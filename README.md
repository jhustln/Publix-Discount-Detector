# Publix-Discount-Detector
Quick script that scans the publix weekly ads page to scan for discounts of a user inputted item in a user inputted store. Integrated with Selenium.


# HOW TO RUN

Download the script:

Download publix_deal_scraper.py

Download requirements.txt


Create a virtual environment:

python3 -m venv venv

source venv/bin/activate  # On Windows: venv\Scripts\activate

Install dependencies:

pip install -r requirements.txt

# DEPENDENCIES

The script requires the following Python packages:
selenium>=4.0.0
beautifulsoup4>=4.9.0
lxml>=4.6.0
These will be automatically installed when you run:

pip install -r requirements.txt

# USAGE

Basic Usage

Activate your virtual environment (if not already activated):

source venv/bin/activate  # On Windows: venv\Scripts\activate

Run the scraper:

python publix_deal_scraper.py

# HOW TO AUTOMATE WITH DISCORD WEBHOOKS

Build Docker image:
**MUST DOWNLOAD AUTOMATED VERSION OF SCRIPT**
docker build -f Dockerfile.k8s -t publix-scraper:latest .

Run the image: docker run -it --rm -e SEARCH_ITEMS="<ITEM>" -e STORE_NUMBER="<4-DIGIT STORE NUMBER>" -e DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/123456789/blahblahblah" publix-scraper:latest

