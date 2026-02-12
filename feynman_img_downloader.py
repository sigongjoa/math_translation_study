import asyncio
import os
from playwright.async_api import async_playwright

async def download_image(url, save_path):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={"Referer": "https://feynmanlectures.caltech.edu/I_01.html"}
        )
        page = await context.new_page()
        print(f"[LOG] Navigating to {url}...")
        
        response = await page.goto(url)
        if response.status == 200:
            content = await response.body()
            with open(save_path, "wb") as f:
                f.write(content)
            print(f"[OK] Downloaded {save_path}")
        else:
            print(f"[ERR] Failed {url}: {response.status}")
        
        await browser.close()

async def main():
    img_dir = "feynman_json/images"
    if not os.path.exists(img_dir):
        os.makedirs(img_dir)
        
    base_url = "https://feynmanlectures.caltech.edu/img/FLP_I/CH01/"
    images = [
        "f01-02_tc_big.svgz",
        "f01-04_tc_big.svgz",
        "f01-05_tc_big.svgz",
        "f01-07_tc_iPad_big_a.svgz",
        "f01-08_tc_big.svgz",
        "f01-10_tc_big.svgz"
    ]
    
    for img in images:
        await download_image(base_url + img, os.path.join(img_dir, img))

if __name__ == "__main__":
    asyncio.run(main())
