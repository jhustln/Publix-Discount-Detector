#!/usr/bin/env python3
"""
Publix Weekly Ad Deal Finder - Automated Discord Notifier
Runs automatically and sends Discord webhook notifications for deals.
Designed for Kubernetes CronJob deployment.
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import re
import os
import json
import requests
from datetime import datetime
from typing import List, Dict, Optional

# Configuration from environment variables
SEARCH_ITEMS = os.getenv('SEARCH_ITEMS', 'chicken').split(',')  # Comma-separated items
STORE_NUMBER = os.getenv('STORE_NUMBER', None)
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')

def setup_driver(headless=True):
    """Set up Chrome WebDriver for containerized environment."""
    options = Options()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    return webdriver.Chrome(options=options)

def scroll_page(driver):
    """Scroll to load all lazy-loaded content."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    for _ in range(5):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def detect_bogo(text):
    """Detect BOGO deals with multiple patterns."""
    text_lower = text.lower()
    
    if re.search(r'buy\s*\d+\s*get\s*\d+', text_lower):
        return True
    
    if 'bogo' in text_lower:
        return True
    
    bogo_phrases = ['buy one get one', 'buy 1 get 1', 'b1g1', 'buy one, get one']
    return any(phrase in text_lower for phrase in bogo_phrases)

def categorize_deal(text, prices):
    """Categorize the type of deal."""
    if detect_bogo(text):
        return "BOGO"
    elif 'save' in text.lower() or re.search(r'save\s*up\s*to', text.lower()):
        return "Discount"
    elif len(prices) > 1:
        return "Price Drop"
    return "Deal"

def extract_deal_info(container):
    """Extract deal information from a product container."""
    try:
        full_text = container.get_text(separator='\n', strip=True)
        
        if not full_text or len(full_text) < 5:
            return None
        
        lines = [l.strip() for l in full_text.split('\n') if l.strip()]
        product_name = lines[0] if lines else 'Unknown Product'
        
        prices = re.findall(r'\$\d+\.\d{2}', full_text)
        current_price = prices[0] if prices else None
        
        is_bogo = detect_bogo(full_text)
        
        savings = None
        savings_match = re.search(r'save\s*up\s*to\s*\$(\d+\.\d{2})', full_text.lower())
        if savings_match:
            savings = f"${savings_match.group(1)}"
        elif not savings_match:
            savings_match = re.search(r'save\s*\$(\d+\.\d{2})', full_text.lower())
            if savings_match:
                savings = f"${savings_match.group(1)}"
        
        deal_description = None
        for line in lines:
            line_lower = line.lower()
            if 'buy' in line_lower and 'get' in line_lower:
                deal_description = line
                break
            elif 'save' in line_lower:
                deal_description = line
                break
        
        deal_type = categorize_deal(full_text, prices)
        
        image_url = None
        img = container.find('img')
        if img:
            image_url = img.get('src') or img.get('data-src')
        
        has_deal = is_bogo or savings or deal_description or len(prices) > 1
        
        if not has_deal:
            return None
        
        return {
            'product_name': product_name,
            'current_price': current_price,
            'savings': savings,
            'deal_type': deal_type,
            'deal_description': deal_description,
            'is_bogo': is_bogo,
            'image_url': image_url,
            'full_text': full_text
        }
        
    except Exception:
        return None

def find_deals(soup):
    """Find all product deals on the page."""
    deals = []
    
    price_elements = soup.find_all(string=re.compile(r'\$\d+\.\d{2}'))
    
    product_containers = set()
    for price_elem in price_elements:
        parent = price_elem.parent
        for _ in range(10):
            if parent and parent.name == 'div':
                classes = parent.get('class', [])
                class_str = ' '.join(classes).lower()
                
                if any(keyword in class_str for keyword in ['product', 'item', 'card', 'deal', 'tile']):
                    product_containers.add(parent)
                    break
                
                if parent.get('data-testid') or parent.get('data-product-id'):
                    product_containers.add(parent)
                    break
            
            parent = parent.parent if parent else None
    
    for container in product_containers:
        deal = extract_deal_info(container)
        if deal:
            deals.append(deal)
    
    return deals

def send_discord_notification(deals, search_item):
    """Send Discord webhook notification about deals found."""
    if not DISCORD_WEBHOOK_URL:
        print("⚠️  No Discord webhook URL configured. Skipping notification.")
        return
    
    if not deals:
        print("ℹ️  No deals to notify about.")
        return
    
    # Create embed
    color = 0x00FF00 if any(d['is_bogo'] for d in deals) else 0x0099FF
    
    embed = {
        "title": f"🛒 Publix Deals Found: {search_item.upper()}",
        "description": f"Found **{len(deals)}** deal(s) for {search_item}!",
        "color": color,
        "timestamp": datetime.utcnow().isoformat(),
        "fields": [],
        "footer": {
            "text": f"Publix Store #{STORE_NUMBER}" if STORE_NUMBER else "All Stores"
        }
    }
    
    # Add up to 10 deals (Discord limit is 25 fields)
    for deal in deals[:10]:
        deal_emoji = "🎁" if deal['is_bogo'] else "💵" if deal['deal_type'] == "Discount" else "📉"
        
        field_value = []
        if deal.get('current_price'):
            field_value.append(f"💰 **Price:** {deal['current_price']}")
        if deal.get('savings'):
            field_value.append(f"💵 **Savings:** {deal['savings']}")
        if deal.get('is_bogo'):
            field_value.append(f"🎁 **BOGO DEAL!**")
        if deal.get('deal_description'):
            field_value.append(f"📋 {deal['deal_description']}")
        
        embed["fields"].append({
            "name": f"{deal_emoji} {deal['product_name']}",
            "value": "\n".join(field_value) if field_value else "Deal available!",
            "inline": False
        })
    
    if len(deals) > 10:
        embed["fields"].append({
            "name": "➕ More Deals",
            "value": f"...and {len(deals) - 10} more deals!",
            "inline": False
        })
    
    # Add summary
    bogo_count = sum(1 for d in deals if d['is_bogo'])
    discount_count = sum(1 for d in deals if d['deal_type'] == 'Discount')
    
    summary = f"📊 **Summary:** {bogo_count} BOGO, {discount_count} Discounts"
    embed["fields"].append({
        "name": "Summary",
        "value": summary,
        "inline": False
    })
    
    # Send webhook
    payload = {
        "username": "Publix Deal Finder",
        "avatar_url": "https://www.publix.com/images/publix-icon.png",
        "embeds": [embed]
    }
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code == 204:
            print(f"✅ Discord notification sent successfully!")
        else:
            print(f"⚠️  Discord notification failed: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Error sending Discord notification: {e}")

def scrape_deals(search_item):
    """Scrape Publix for deals on a specific item."""
    print(f"🔍 Searching for: '{search_item}'")
    if STORE_NUMBER:
        print(f"📍 Store: #{STORE_NUMBER}")
    else:
        print(f"📍 Store: All stores")
    
    # Build URL
    if STORE_NUMBER:
        url = f"https://www.publix.com/savings/weekly-ad/view-all?storeNumber={STORE_NUMBER}"
    else:
        url = "https://www.publix.com/savings/weekly-ad/view-all"
    
    driver = setup_driver(headless=True)
    
    try:
        print("🌐 Loading weekly ad page...")
        driver.get(url)
        
        print("⏳ Waiting for page to load...")
        time.sleep(5)
        
        print("📜 Scrolling to load all products...")
        scroll_page(driver)
        
        print("🔍 Analyzing page...")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        all_deals = find_deals(soup)
        print(f"✅ Found {len(all_deals)} total products")
        
        # Filter by search term
        search_lower = search_item.lower()
        matching_deals = [d for d in all_deals if search_lower in d['product_name'].lower()]
        
        print(f"✅ Found {len(matching_deals)} matching '{search_item}'")
        
        return matching_deals
    
    except Exception as e:
        print(f"❌ Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    finally:
        driver.quit()

def main():
    """Main function for automated execution."""
    print("=" * 80)
    print("  PUBLIX WEEKLY AD SCRAPER - AUTOMATED MODE")
    print("=" * 80)
    print(f"⏰ Run Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔍 Search Items: {', '.join(SEARCH_ITEMS)}")
    print(f"📍 Store: {STORE_NUMBER if STORE_NUMBER else 'All Stores'}")
    print(f"🔔 Discord Webhook: {'Configured ✅' if DISCORD_WEBHOOK_URL else 'Not Configured ❌'}")
    print("=" * 80)
    print()
    
    all_results = {}
    
    for search_item in SEARCH_ITEMS:
        search_item = search_item.strip()
        if not search_item:
            continue
        
        deals = scrape_deals(search_item)
        all_results[search_item] = deals
        
        # Send Discord notification
        if deals:
            send_discord_notification(deals, search_item)
            
            
            print(f"\n🎉 Deals for '{search_item}':")
            for i, deal in enumerate(deals, 1):
                print(f"  {i}. {deal['product_name']}")
                if deal.get('is_bogo'):
                    print(f"     🎁 BOGO!")
                if deal.get('current_price'):
                    print(f"     💰 {deal['current_price']}")
        else:
            print(f"\n😞 No deals found for '{search_item}'")
        
        print()
        
        # Wait between searches to be respectful
        if search_item != SEARCH_ITEMS[-1].strip():
            time.sleep(3)
    
    
    total_deals = sum(len(deals) for deals in all_results.values())
    print("=" * 80)
    print(f"📊 SUMMARY: Found {total_deals} total deals across all searches")
    print("=" * 80)
    
    

if __name__ == "__main__":
    main()