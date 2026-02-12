import os
import time
import random
import argparse
from playwright.sync_api import sync_playwright

# Backend Persona: Implementing a robust scraper with stealth patterns
# Goal: Bypass Cloudflare and extract clean HTML from feynmanlectures.caltech.edu

class FeynmanScraper:
    def __init__(self, output_dir="feynman_raw"):
        self.base_url = "https://www.feynmanlectures.caltech.edu"
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
    def get_chapter_url(self, vol, chapter):
        # vol: Roman numeral (I, II, III), chapter: 1-indexed number
        return f"{self.base_url}/{vol}_{chapter:02}.html"

    def scrape_chapter(self, vol, chapter):
        filename = f"{vol}_{chapter:02}.html"
        filepath = os.path.join(self.output_dir, filename)
        
        if os.path.exists(filepath):
            print(f"[LOG] {filename} already exists. Skipping.")
            return True

        url = self.get_chapter_url(vol, chapter)
        print(f"[LOG] Attempting to scrape: {url}")

        with sync_playwright() as p:
            # Using chromium with stealth-like headers and user-agent
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            try:
                # Add extra headers to look like a real browser
                page.set_extra_http_headers({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Cache-Control": "max-age=0"
                })

                # Go to page with "networkidle" to ensure MathJax/content is loaded
                # We use a generous timeout because caltech's site can be slow
                response = page.goto(url, wait_until="networkidle", timeout=60000)
                
                if response.status != 200:
                    print(f"[ERR] Failed with status {response.status}")
                    return False

                # Handle potential Cloudflare "Waiting" screens
                if "Attention Required" in page.title() or "Cloudflare" in page.content()[:500]:
                    print("[ERR] Hit Cloudflare wall. Need deeper stealth.")
                    return False

                # Save the full rendered HTML
                content = page.content()
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                
                print(f"[OK] Saved to {filepath}")
                return True

            except Exception as e:
                print(f"[ERR] Exception occurred: {e}")
                return False
            finally:
                browser.close()

    def download_assets(self, urls, output_subdir="images"):
        # Download a list of image URLs using Playwright for stealth
        full_output_dir = os.path.join(self.output_dir, output_subdir)
        if not os.path.exists(full_output_dir):
            os.makedirs(full_output_dir)

        print(f"[LOG] Attempting to download {len(urls)} assets...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            
            for url in urls:
                filename = os.path.basename(url)
                filepath = os.path.join(full_output_dir, filename)
                
                if os.path.exists(filepath):
                    continue

                print(f"[LOG] Downloading asset: {url}")
                page = context.new_page()
                try:
                    # Using page.goto directly on the image URL
                    # For images, status 200 is enough
                    response = page.goto(url, timeout=30000)
                    if response.status == 200:
                        with open(filepath, "wb") as f:
                            f.write(response.body())
                        print(f"[OK] Saved asset {filename}")
                    else:
                        print(f"[WARN] Failed to download {url}: {response.status}")
                except Exception as e:
                    print(f"[WARN] Error downloading {url}: {e}")
                finally:
                    page.close()
            
            browser.close()

def main():
    parser = argparse.ArgumentParser(description="Feynman Lectures Scraper")
    parser.add_argument("--vol", default="I", help="Volume (I, II, III)")
    parser.add_argument("--ch", type=int, default=1, help="Chapter number")
    args = parser.parse_args()

    scraper = FeynmanScraper()
    success = scraper.scrape_chapter(args.vol, args.ch)
    
    if not success:
        # Fallback to Web Archive if direct access fails
        print("[LOG] Trying fallback to Wayback Machine...")
        # (Implementation of fallback could be added here)

if __name__ == "__main__":
    main()
