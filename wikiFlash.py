import os
import time
import wikipedia
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ---------------- Folder ----------------
def create_folder(name="screenshots"):
    if not os.path.exists(name):
        os.makedirs(name)
    return name

# ---------------- Wikipedia search ----------------
def search_wikipedia(word, max_results=5):
    try:
        results = wikipedia.search(word, max_results, False)
        return results[:max_results]
    except Exception as e:
        print(f"Search error: {e}")
        return []

# ---------------- Skip disambiguation pages ----------------
def is_disambiguation_page(driver):
    try:
        # Check if body has class "disambiguation"
              
        body_class = driver.execute_script("return document.body.className;")
        if "disambiguation" in body_class.lower():
            return True
        # Also check title for "disambiguation"
        title = driver.title.lower()
        if "disambiguation" in title:
            return True
        return False
    except:
        return False

# ---------------- Aspect ratio ----------------
def adjust_aspect_ratio_safe(left, top, right, bottom, target_ratio, im_width, im_height):
    width = right - left
    height = bottom - top
    current_ratio = width / height

    if current_ratio > target_ratio:
        new_height = width / target_ratio
        expand = new_height - height
        top_new = max(top - expand / 2, 0)
        bottom_new = min(bottom + expand / 2, im_height)
        top, bottom = top_new, bottom_new
        height = bottom - top
        width = height * target_ratio
        center_x = (left + right) / 2
        left = max(center_x - width / 2, 0)
        right = min(center_x + width / 2, im_width)
    else:
        new_width = height * target_ratio
        expand = new_width - width
        left_new = max(left - expand / 2, 0)
        right_new = min(right + expand / 2, im_width)
        left, right = left_new, right_new
        width = right - left
        height = width / target_ratio
        center_y = (top + bottom) / 2
        top = max(center_y - height / 2, 0)
        bottom = min(center_y + height / 2, im_height)

    return int(left), int(top), int(right), int(bottom)

# ---------------- Highlight HTML ----------------
def highlight_word_in_html(driver, word):
    js_code = f"""
    const word = {repr(word)};
    const regex = new RegExp(`\\\\b${{word}}\\\\b`, 'gi');
    function walk(node) {{
        if(node.nodeType === 3) {{
            if(regex.test(node.nodeValue)) {{
                const span = document.createElement('span');
                span.innerHTML = node.nodeValue.replace(regex, '<mark style="background: yellow; color: black;">$&</mark>'); //if you dont find a word like waited you can change the $& to $&ed
                node.parentNode.replaceChild(span, node);
            }}
        }} else if(node.nodeType === 1 && node.tagName !== 'SCRIPT' && node.tagName !== 'STYLE' && node.tagName !== 'NOSCRIPT') {{
            for(let i=0;i<node.childNodes.length;i++) walk(node.childNodes[i]);
        }}
    }}
    walk(document.body);
    """
    driver.execute_script(js_code)

# ---------------- OCR & crop ----------------
def ocr_find_word_and_crop(screenshot_path, word, folder, start_count=0, padding_factor=15, aspect_ratio=16/9, target_size=(1920,1080), suffix=""):
    word = word + suffix

    try:
        im = Image.open(screenshot_path)
        data = pytesseract.image_to_data(im, output_type=pytesseract.Output.DICT)
    except Exception as e:
        return start_count

    count = start_count
    for i, text in enumerate(data['text']):     
        if text.strip() == "":
            continue

        # Ensure the word is not part of another word (e.g., "cat" in "category")
        words = [w.strip(".,!?;:") for w in text.split()]
        if word.lower() not in [w.lower() for w in words]:
            continue


        x, y = data['left'][i], data['top'][i]
        w, h = data['width'][i], data['height'][i]

        # Zoom out using padding factor
        cx, cy = x + w / 2, y + h / 2
        new_w = w * padding_factor
        new_h = h * padding_factor

        if(cx - new_w / 2 < 0 or cy - new_h / 2 < 0 or cx + new_w / 2 > im.width or cy + new_h / 2 > im.height):
            continue  # Skip if padding goes out of bounds00
        
        left = cx - new_w / 2
        right = cx + new_w / 2  
        top = cy - new_h / 2
        bottom = cy + new_h / 2

        # Adjust to aspect ratio
        left, top, right, bottom = adjust_aspect_ratio_safe(left, top, right, bottom, aspect_ratio, im.width, im.height)

        # Crop and resize   ssssss
        cropped = im.crop((left, top, right, bottom))
        cropped = cropped.resize(target_size, Image.LANCZOS)

        # Add optional suffix to the filename
        filename_cropped = os.path.join(folder, f"{word}_{count+1}.png")
        cropped.save(filename_cropped)
        count += 1

        # Exit if screenshot count reaches 300
        if count >= 300:
            return count

    return count

# ---------------- Screenshot handler ----------------
def find_and_screenshot_occurrences(driver, word, folder, start_count, padding_factor, aspect_ratio, target_size, highlight_html=True, progress_bar=None):
    if highlight_html:
        highlight_word_in_html(driver, word)
        time.sleep(0.5)

    # Full-page screenshot
    total_height = driver.execute_script("return document.body.scrollHeight")
    max_height = 10000  # Cap the total height to prevent issues with Tesseract
    driver.set_window_size(1920, min(total_height, max_height))
    screenshot_path = os.path.join(folder, "_temp.png")
    driver.save_screenshot(screenshot_path)

    # OCR crop for each occurrence
    new_count = ocr_find_word_and_crop(screenshot_path, word, folder, start_count, padding_factor, aspect_ratio, target_size)

    if os.path.exists(screenshot_path):
        os.remove(screenshot_path)

    if progress_bar:
        progress_bar.update(new_count - start_count)

    return new_count

# ---------------- Main ----------------
def screenshot_pages(word, padding_factor=3, aspect_ratio=16/9, target_size=(1920,1080), highlight_html=True, max_results=5, word_count=1, total_words=1):
    folder = create_folder()

    
    pages = search_wikipedia(word, max_results)
    if not pages:
        print("No pages found.")
        return

    print()
    print(f"Found {len(pages)} pages for '{word}':")
    for p in pages:
        print(f" - {p}")

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    global_count = 0
    spinner = itertools.cycle(['-', '\\', '|', '/'])
    start_time = time.time()
    stop_progress = threading.Event()

    def display_progress():
        print()
        while not stop_progress.is_set():
            elapsed_time = time.time() - start_time
            progress = int((global_count / 300) * 50) if global_count > 0 else 0
            bar = f"[{'#' * progress}{'.' * (50 - progress)}]"
            sys.stdout.write(
                f"\rWord: {word} (#{word_count}/{total_words}) | {bar} {global_count}/300 screenshots | {next(spinner)} | Elapsed: {elapsed_time:.1f}s "
            )
            sys.stdout.flush()
            time.sleep(0.1)

    def process_pages():
        nonlocal global_count
        for i, page_title in enumerate(pages, start=1):
            url = f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"
            driver.get(url)
            time.sleep(2)

            if is_disambiguation_page(driver):
                continue

            global_count = find_and_screenshot_occurrences(
                driver, word, folder, global_count, padding_factor, aspect_ratio, target_size, highlight_html
            )

            # Exit if screenshot count reaches 300
            if global_count >= 300:
                break

        driver.quit()
        print(f"\n✅ All screenshots saved in '{folder}/'.")


        stop_progress.set()

    # Run the progress display in a separate thread
    progress_thread = threading.Thread(target=display_progress)
    progress_thread.start()
    # Run the page processing in the main thread
    process_pages()

    # Wait for the progress thread to finish
    progress_thread.join()

import cv2
import glob
import shutil
import itertools
import sys
import threading
def create_video_from_screenshots(folder="screenshots", output_file="output_video.mp4", frame_time=0.05):
    """
    Compiles all PNG screenshots in the folder into a video.
    
    frame_time: duration of each screenshot in seconds
    """
    images = sorted(glob.glob(os.path.join(folder, "*.png")))
    if not images:
        print(" No screenshots found to create video.")
        return

    # Read first image to get dimensions
    frame = cv2.imread(images[0])
    height, width, layers = frame.shape

    # FPS = 1/frame_time
    fps = 1 / frame_time

    # Calculate minimum number of frames for 15 seconds
    min_frames = int(15 * fps)

    # Extend the image list to meet the minimum duration
    while len(images) < min_frames:
        images.extend(images)  # Duplicate the list
    images = images[:min_frames]  # Trim to exact number of frames

    # Define VideoWriter
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video = cv2.VideoWriter(output_file, fourcc, fps, (width, height))

    for img_path in images:
        frame = cv2.imread(img_path)
        video.write(frame)

    video.release() 
    print(f"\n Video saved as {output_file}, each frame duration: {frame_time} seconds")


# ---------------- Run ----------------
if __name__ == "__main__":
    print("Reading words from 'input_text.txt'...")
    with open("input_text.txt", "r", encoding="utf-8") as file:
        text = file.read()
    words = list(dict.fromkeys(word.strip(".,!?;:\n").lower() for word in text.split()))  
    print("Parsed words:", words)

    print()

    padding_input = input("Padding factor (default 15): ")
    aspect_input = input("Aspect ratio W/H (default 16/9): ")
    width_input = input("Width (default 1920): ")
    height_input = input("Height (default 1080): ")
    highlight_input = input("Highlight HTML? (y/n, default y): ")

    padding_factor = float(padding_input) if padding_input.strip() else 15
    aspect_ratio = float(aspect_input) if aspect_input.strip() else 16/9
    target_width = int(width_input) if width_input.strip() else 1920
    target_height = int(height_input) if height_input.strip() else 1080
    highlight_html = highlight_input.strip().lower() != 'n'

    word_count = 1
    def process_word(word, word_count):
        screenshot_pages(word, padding_factor, aspect_ratio, target_size=(target_width, target_height), highlight_html=highlight_html, max_results=5, word_count=word_count, total_words=len(words))
        create_video_from_screenshots(folder="screenshots", output_file=f"{word}.mp4", frame_time=0.05)

        # Delete the screenshots folder after creating the video
        if os.path.exists("screenshots"):
            shutil.rmtree("screenshots")
            print(f" 'screenshots' folder deleted for word: {word}")

    for word in words:
        process_word(word, word_count)
        word_count += 1

    