import asyncio
import os
from playwright.async_api import async_playwright

URL = "https://sprout-frontend-330254514404.us-east1.run.app"
ARTIFACT_DIR = "/config/.gemini/antigravity/brain/c63aad97-15df-4fe1-9f30-c73a7bd77439"
VIDEO_DIR = os.path.join(ARTIFACT_DIR, "video_temp")

async def record_demo():
    os.makedirs(VIDEO_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            record_video_dir=VIDEO_DIR,
            record_video_size={"width": 1280, "height": 720},
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        
        print(f"Navigating to {URL}...")
        await page.goto(URL, wait_until="networkidle")
        await asyncio.sleep(2)
        
        # 1. First prompt: Show me my plants
        print("Sending prompt 1: Show me my plants...")
        await page.click("button.example-chip:has-text('Show me my plants')")
        
        # Wait for agent response bubble with rich card to appear
        print("Waiting for response 1...")
        await page.wait_for_selector(".msg.agent", timeout=30000)
        await asyncio.sleep(6) # Give time for viewer to see response
        
        # 2. Second prompt: Add a Monstera in the living room
        print("Sending prompt 2: Add a Monstera in the living room...")
        await page.fill("#input", "Add a Monstera in the living room with a watering interval of 7 days")
        await page.click("form button")
        
        # Wait for second response
        print("Waiting for response 2...")
        await page.wait_for_function("document.querySelectorAll('.msg.agent').length >= 2", timeout=30000)
        await asyncio.sleep(8) # Give time to show tool execution and pet toxicity warning card
        
        print("Closing context...")
        video_obj = page.video
        await context.close()
        await browser.close()
        
        if video_obj:
            video_path = await video_obj.path()
            target_path = os.path.join(ARTIFACT_DIR, "sprout_demo.webm")
            if os.path.exists(video_path):
                os.rename(video_path, target_path)
                print(f"Demo video saved to: {target_path}")

asyncio.run(record_demo())
