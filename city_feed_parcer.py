import os
import json
import re
import feedparser
from openai import OpenAI

# 1. Configuration: Add your department map
# Note: feedparser uses the .xml endpoint, not the .json one your frontend used
FEED_MAP = {
    "City of Chattanooga": "PdN33cuT336K8vmC",
    "Events": "UCma6BIDGdYc5ElW",
    "City Job Postings": "qKe272dsP2brLIb5",
    "Mayor's Updates": "LTs3Zw710ixkkYP7",
    "311": "NQ181GaRdZgtNKvu",
    "Arts, Culture, & Creative Economy": "lGTNdiDM9ecyOkNw",
    "City Council": "Dg85HPBbJpF9xdPh",
    "Community Development": "eIqe3O4Mlm44tyoP",
    "Early Learning": "mXQ7ghtQUvXGP9FW",
    "Family Justice Center": "GNEGjqByj59C1blF",
    "Fire": "SrwJ0VaTUmXjeUjT",
    "Library": "US5lBhTDrOIrDydn",
    "Mayor's Council for Women": "1YjbzL9irBfdGl7C",
    "Mayor's Council on Disability": "yBRlakwD2dcDSAd1",
    "Mayor's Council on Livability and Aging": "145MgxnRLU94ZbCa",
    "Mayor's Youth Council": "82uM5mcbpkIo93Od",
    "National Park City": "He5YPMK6X7e3y8iM",
    "Office of Community Health": "eSt1Pg9lB8gSmXYJ",
    "Office of Family Empowerment": "vgd2eIj4ItLXG65T",
    "Outdoor Chattanooga": "XVe7oDNfYyUXZOSu",
    "Parks & Outdoors": "8hFrcyckecmlRG7k",
    "Police": "fcbU6eKnKMNpgYtd",
    "Public Works": "zHd32de2UhbxklCC",
    "Regional Planning Agency": "cFN86DkPgWksrrOs",
    "Wastewater": "DvnvLL2j92fAm7dz"
}

DATA_FILE = "processed_city_feed.json"
PROCESSED_LOG = "processed_city_guids.txt"

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def load_processed_guids():
    if os.path.exists(PROCESSED_LOG):
        with open(PROCESSED_LOG, "r") as f:
            return set(line.strip() for line in f)
    return set()

def save_processed_guid(guid):
    with open(PROCESSED_LOG, "a") as f:
        f.write(f"{guid}\n")

def load_existing_feed():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def clean_html_tags(text):
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

# 2. Update the AI Prompt to look for public events
def check_if_event(description):
    prompt = f"""
    You are an assistant for the City of Chattanooga. Analyze the following social media post text and determine if it is advertising a future event that is open to the public. 
    
    Rules:
    - Set 'is_event' to true ONLY if there is a specific mention of a gathering, meeting, festival, class, or public occurrence with an implied or stated date/time.
    - Set 'is_event' to false if it is just a general announcement, a recap of a past event, a job posting, or generic news.

    Description: {description}

    Respond ONLY with a valid JSON object matching this schema:
    {{
      "is_event": boolean
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"is_event": False}

def main():
    print("Running City Feed pipeline...")
    processed_guids = load_processed_guids()
    existing_feed = load_existing_feed()
    new_entries_found = False
    
    # 3. Loop through all departments
    for dept_name, feed_id in FEED_MAP.items():
        print(f"Processing feed: {dept_name}...")
        rss_url = f"https://rss.app/feeds/{feed_id}.xml"
        feed = feedparser.parse(rss_url)
        
        for entry in reversed(feed.entries):
            guid = entry.get("id") or entry.get("link")
            if guid in processed_guids:
                continue
                
            summary_content = entry.get("summary", "") or entry.get("description", "")
            clean_description = clean_html_tags(summary_content)
            clean_description = re.sub(r'^\[.*?\]', '', clean_description).strip()

            if not clean_description or len(clean_description) < 20:
                save_processed_guid(guid)
                processed_guids.add(guid)
                continue

            image_url = None
            img_match = re.search(r'<img[^>]+src="([^">]+)"', summary_content)
            if img_match:
                image_url = img_match.group(1)

            # Analyze the post
            ai_decision = check_if_event(clean_description)
            is_event = ai_decision.get("is_event", False)
            
            # Format authors array so the frontend doesn't break
            authors_data = entry.get("authors", [])
            if not authors_data and entry.get("author"):
                authors_data = [{"name": entry.get("author")}]

            new_post = {
                "url": entry.get("link", ""),
                "image": image_url,
                "content_text": clean_description,
                "department": dept_name,          # Hardcode the department name from our loop
                "is_event": is_event,             # The AI's decision
                "date_published": entry.get("published", entry.get("updated", "")),
                "authors": authors_data 
            }
            
            existing_feed.insert(0, new_post)
            new_entries_found = True
                
            save_processed_guid(guid)
            processed_guids.add(guid)

    if new_entries_found:
        # Sort the entire combined list by date (newest first) before saving
        # Since RSS date formats can vary, we just rely on the order of addition, 
        # but a robust pipeline might parse the datetime objects here.
        
        # Keep the master list manageable (e.g., top 300 posts across the city)
        existing_feed = existing_feed[:300] 
        with open(DATA_FILE, "w") as f:
            json.dump(existing_feed, f, indent=2)
            
    print("City Feed pipeline complete.")

if __name__ == "__main__":
    main()
