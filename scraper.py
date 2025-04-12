import requests
from bs4 import BeautifulSoup
import re
from playwright.sync_api import sync_playwright
import os
import time
from PIL import Image
import io

def get_trending_ai_repos(url="https://github.com/trending/python?since=daily&spoken_language_code=en"):
    """
    Fetches the GitHub trending page and extracts repositories potentially related to AI.

    Args:
        url (str): The URL of the GitHub trending page to scrape.

    Returns:
        list: A list of tuples, where each tuple contains (repo_name, repo_url).
    """
    ai_keywords = ['ai', 'llm', 'artificial intelligence', 'machine learning', 'deep learning', 'neural network']
    ai_repos = []
    headers = {'User-Agent': 'Mozilla/5.0'} # Define headers once

    try:
        print(f"Fetching trending page: {url}")
        response = requests.get(url, headers=headers, timeout=30) # Add timeout to requests
        response.raise_for_status() # Raise an exception for bad status codes

        soup = BeautifulSoup(response.text, 'html.parser')
        # Refine selector for robustness if GitHub changes structure slightly
        repo_list = soup.select('article.Box-row')

        if not repo_list:
            print("Could not find repository list using selector 'article.Box-row'. HTML structure might have changed.")
            return []

        print(f"Found {len(repo_list)} repositories on the trending page. Filtering for AI keywords...")

        for repo in repo_list:
            # Use more specific selectors and handle potential missing elements gracefully
            title_element = repo.select_one('h2.h3 a')
            if not title_element or 'href' not in title_element.attrs:
                print("  Skipping repo: Could not find title link.")
                continue

            repo_url_path = title_element['href']
            repo_name = repo_url_path.strip('/')
            repo_url = f"https://github.com{repo_url_path}"

            description_element = repo.select_one('p.col-9')
            description = description_element.get_text(strip=True).lower() if description_element else ""

            # Check for AI keywords
            repo_name_lower = repo_name.lower()
            if any(keyword in description for keyword in ai_keywords) or \
               any(keyword in repo_name_lower for keyword in ai_keywords):
                print(f"  Found potential AI repo: {repo_name} ({repo_url})")
                ai_repos.append((repo_name, repo_url))
            # else:
            #     print(f"  Skipping repo (no keywords): {repo_name}") # Optional: for debugging non-matches

    except requests.exceptions.Timeout:
        print(f"Error: Timeout occurred while fetching {url}")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching trending page {url}: {e}")
    except Exception as e:
        print(f"An error occurred during parsing trending page: {e}")

    print(f"Finished filtering. Found {len(ai_repos)} potential AI repositories.")
    return ai_repos


def capture_readme_screenshot(repo_url, output_dir="screenshots"):
    """
    Navigates to a GitHub repo URL, waits for the README section to be visible,
    takes its screenshot, and crops it to a 4x3 aspect ratio from the top.

    Args:
        repo_url (str): The URL of the GitHub repository.
        output_dir (str): The directory to save screenshots.
    """
    browser = None # Initialize browser to None
    readme_element = None # Initialize readme_element
    try:
        repo_parts = [part for part in repo_url.split('/') if part]
        repo_name = f"{repo_parts[-2]}_{repo_parts[-1]}" if len(repo_parts) >= 2 else re.sub(r'[^\w\-]+', '_', repo_url)
        screenshot_path = os.path.join(output_dir, f"{repo_name}_readme_4x3.png")

        readme_selector = "#readme article.markdown-body"
        fallback_selector = "article.markdown-body[itemprop='text']"
        alternative_selector = "div.markdown-body.entry-content"
        selectors_to_try = [readme_selector, fallback_selector, alternative_selector]

        os.makedirs(output_dir, exist_ok=True)

        print(f"Attempting to capture README screenshot for: {repo_url}")

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            print(f"  Navigating to {repo_url} (wait_until='load')...")
            page.goto(repo_url, wait_until='load', timeout=90000) # Increased timeout to 90s
            print("  Navigation complete.")

            # Try selectors sequentially, waiting for visibility
            for i, selector in enumerate(selectors_to_try):
                print(f"  Attempting selector {i+1}/{len(selectors_to_try)}: '{selector}' (waiting for visible state)...")
                try:
                    # Wait for the element matching the selector to be visible
                    readme_element = page.wait_for_selector(selector, state='visible', timeout=20000) # 20s timeout per selector
                    print(f"  Element found and visible with selector: '{selector}'")
                    break # Found a working selector, exit loop
                except Exception as e: # Catches TimeoutError, etc.
                    print(f"  Selector '{selector}' timed out or failed: {str(e).splitlines()[0]}") # Show brief error
                    readme_element = None # Ensure it's None if wait fails

            if readme_element:
                print("  Element located. Taking screenshot...")
                # Add a tiny sleep just before screenshot in case visibility triggered slightly early
                time.sleep(0.2)
                screenshot_bytes = readme_element.screenshot()

                print("  Processing screenshot...")
                # Import necessary PIL components if not already globally imported
                # from PIL import Image, UnidentifiedImageError
                # import io
                try:
                    img = Image.open(io.BytesIO(screenshot_bytes))
                except UnidentifiedImageError:
                    print("  Error: Could not identify image file from screenshot bytes.")
                    img = None # Ensure img is None

                if img:
                    original_width, original_height = img.size

                    if original_width <= 0 or original_height <= 0:
                        print(f"  Skipping save: Invalid image dimensions ({original_width}x{original_height}).")
                        if img: img.close()
                    else:
                        padding = 2
                        new_width = original_width + 2 * padding

                        # Ensure mode is suitable for creating a new image (e.g., RGB/RGBA)
                        current_mode = img.mode
                        img_to_paste = img # Keep original reference for closing
                        if current_mode == 'P':
                            img = img.convert('RGBA')
                            current_mode = 'RGBA'
                        elif current_mode == 'L': # Grayscale
                            img = img.convert('RGB')
                            current_mode = 'RGB'
                        elif current_mode == 'LA': # Grayscale with Alpha
                             img = img.convert('RGBA')
                             current_mode = 'RGBA'

                        # Create a new image with white background
                        bg_color = (255, 255, 255) # Default for RGB
                        if current_mode == 'RGBA':
                            bg_color = (255, 255, 255, 255) # White opaque for RGBA

                        try:
                            bordered_img = Image.new(current_mode, (new_width, original_height), bg_color)

                            # Paste the original image onto the new background, offset by padding
                            bordered_img.paste(img, (padding, 0))
                            img.close() # Close the (potentially converted) image object
                            if img is not img_to_paste: img_to_paste.close() # Close original if converted

                            # Calculate target height based on the NEW width for 4:3 ratio
                            target_height = int(new_width * 3 / 4)

                            print(f"  Original dims: {original_width}x{original_height}. New width (padded): {new_width}px. Target 4:3 height: {target_height}px.")

                            # Decide whether to crop vertically based on original height vs target height
                            if original_height > target_height:
                                # Crop the bordered image vertically
                                final_img = bordered_img.crop((0, 0, new_width, target_height))
                                print(f"  Cropping padded image to {new_width}x{target_height} (4:3).")
                            else:
                                # Use the bordered image without vertical cropping (it's already shorter/equal than 4:3)
                                final_img = bordered_img
                                print(f"  Image height ({original_height}px) <= target 4:3 height ({target_height}px). Saving padded image.")

                            final_img.save(screenshot_path)
                            print(f"  Screenshot saved to: {screenshot_path}")
                            final_img.close() # Close the final image object
                            bordered_img.close() # Close the intermediate bordered image

                        except Exception as img_err:
                             print(f"  Error during image processing: {img_err}")
                             # Ensure all image objects are closed on error
                             if 'img' in locals() and img: img.close()
                             if 'img_to_paste' in locals() and img_to_paste: img_to_paste.close()
                             if 'bordered_img' in locals() and bordered_img: bordered_img.close()
                             if 'final_img' in locals() and final_img: final_img.close()

                    # Explicitly close the initial image object if somehow still open
                    # (should be handled by logic above)
                    if 'img_to_paste' in locals() and img_to_paste:
                         try: img_to_paste.close() # Final check
                         except: pass

                else: # Handle case where img could not be opened
                    print(f"  Could not process screenshot for {repo_url} (Image.open failed)")

            else:
                 print(f"  Could not find a visible README element using any selectors on {repo_url}")

            print("  Closing browser...")
            browser.close()
            browser = None # Reset browser variable after closing
            print("  Browser closed.")

    except Exception as e:
        # Log the specific repo URL where the error occurred
        print(f"  Overall error processing {repo_url}: {e}")
        # Ensure browser is closed in case of error
        if browser and browser.is_connected():
            print("  Closing browser due to overall error...")
            try:
                browser.close()
            except Exception as close_err:
                print(f"    Error closing browser: {close_err}")
        # Re-raise the exception if needed, or just log and continue
        # raise e # Uncomment to stop execution on first error


if __name__ == "__main__":
    trending_repos = get_trending_ai_repos()
    if trending_repos:
        print("\nPotential AI Trending Repositories:")
        for i, (name, url) in enumerate(trending_repos):
            print(f"{i+1}. {name}: {url}") # Number the list

        print("\nCapturing README screenshots...")
        # Limit processing for testing (adjust as needed)
        repos_to_process = trending_repos[:3]
        # repos_to_process = trending_repos # Uncomment to process all

        print(f"(Processing first {len(repos_to_process)} repositories for screenshots)")

        for i, (name, url) in enumerate(repos_to_process):
            print(f"\n--- Processing repo {i+1}/{len(repos_to_process)}: {name} ---")
            capture_readme_screenshot(url)
            # Add a slightly longer delay, maybe dynamic based on success/failure?
            print("  Pausing briefly before next repo...")
            time.sleep(5) # 5-second delay

        print("\n--- Finished capturing screenshots. ---")
    else:
        print("No AI-related trending repositories found.")
