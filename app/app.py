from flask import Flask, render_template, request, jsonify, Response, url_for, redirect
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
import os
import uuid
import io
import re
import requests
import instaloader
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import pickle
import logging

app = Flask(__name__)
media_dir = 'media'
os.makedirs(media_dir, exist_ok=True)
L = instaloader.Instaloader()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Selenium WebDriver
def get_driver():
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Load cookies for Instagram login
def load_cookies(driver):
    try:
        driver.get("https://www.instagram.com/")
        time.sleep(3)
        if os.path.exists("cookies.pkl"):
            with open("cookies.pkl", "rb") as file:
                cookies = pickle.load(file)
            for cookie in cookies:
                driver.add_cookie(cookie)
            logger.info("Cookies loaded successfully!")
            return True
        else:
            logger.warning("No saved cookies found! Please log in first.")
            return False
    except Exception as e:
        logger.error(f"Error loading cookies: {e}")
        return False

# Extract Instagram posts
def extract_posts(soup, limit=10):
    posts = []
    post_containers = soup.find_all("div", {"class": "x1lliihq x1n2onr6 xh8yej3 x4gyw5p x11i5rnm x1ntc13c x9i3mqj x2pgyrj"})
    for container in post_containers[:limit]:
        post_data = {}
        try:
            post_url = "https://www.instagram.com" + container.find("a")["href"]
            post_data["post_url"] = post_url
        except:
            post_data["post_url"] = "No URL"
        try:
            img_tag = container.find("img", {"class": "x5yr21d xu96u03 x10l6tqk x13vifvy x87ps6o xh8yej3"})
            caption = img_tag["alt"]
            post_data["caption"] = caption
        except:
            post_data["caption"] = "No caption"
        posts.append(post_data)
    return posts

# Scrape Instagram profiles
def scrape_instagram(instagram_pages, post_limit=10):
    driver = get_driver()
    if not load_cookies(driver):
        driver.quit()
        return {"error": "No cookies found. Please make sure cookies.pkl exists."}
    driver.refresh()
    time.sleep(3)
    output = {}
    for page in instagram_pages:
        page = page.strip()
        if not page.startswith("https://"):
            page = f"https://www.instagram.com/{page.strip('/')}/"
        logger.info(f"Scraping: {page}")
        driver.get(page)
        time.sleep(5)
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except:
            output[page] = {"error": f"Failed to load {page}"}
            continue
        soup = BeautifulSoup(driver.page_source, "html.parser")
        posts = extract_posts(soup, int(post_limit))
        output[page] = posts
    driver.quit()
    return output

# Extract shortcode from Instagram URL
def extract_shortcode(url):
    patterns = [
        r'/p/([A-Za-z0-9_-]+)/?',
        r'/reel/([A-Za-z0-9_-]+)/?',
        r'/tv/([A-Za-z0-9_-]+)/?',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip('/').split('/')
    if 'p' in path_parts:
        idx = path_parts.index('p')
        if idx + 1 < len(path_parts):
            return path_parts[idx + 1]
    if 'reel' in path_parts:
        idx = path_parts.index('reel')
        if idx + 1 < len(path_parts):
            return path_parts[idx + 1]
    if 'tv' in path_parts:
        idx = path_parts.index('tv')
        if idx + 1 < len(path_parts):
            return path_parts[idx + 1]
    if len(path_parts) >= 3 and path_parts[1] == 'reel':
        return path_parts[2]
    for part in path_parts:
        if 10 <= len(part) <= 12 and re.match(r'^[A-Za-z0-9_-]+$', part):
            return part
    return None

# Fetch media from Instagram post
def fetch_media(post_url):
    try:
        shortcode = extract_shortcode(post_url)
        if not shortcode:
            return [], "Invalid URL format. Could not extract post shortcode from {post_url}", None
        logger.info(f"Extracted shortcode: {shortcode}")
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        media_urls = []
        caption = post.caption if post.caption else "No caption available"
        if post.typename == 'GraphSidecar':
            for node in post.get_sidecar_nodes():
                if node.is_video:
                    video_id = str(uuid.uuid4())
                    media_urls.append({
                        "type": "video", 
                        "id": video_id,
                        "original_url": node.video_url,
                        "preview_url": url_for('preview_media', media_id=video_id, media_type='video'),
                        "caption": caption
                    })
                else:
                    image_id = str(uuid.uuid4())
                    media_urls.append({
                        "type": "image", 
                        "id": image_id,
                        "original_url": node.display_url,
                        "preview_url": url_for('preview_media', media_id=image_id, media_type='image'),
                        "caption": caption
                    })
        else:
            if post.is_video:
                video_id = str(uuid.uuid4())
                media_urls.append({
                    "type": "video", 
                    "id": video_id,
                    "original_url": post.video_url,
                    "preview_url": url_for('preview_media', media_id=video_id, media_type='video'),
                    "caption": caption
                })
            if not post.is_video and post.url:
                image_id = str(uuid.uuid4())
                media_urls.append({
                    "type": "image", 
                    "id": image_id,
                    "original_url": post.url,
                    "preview_url": url_for('preview_media', media_id=image_id, media_type='image'),
                    "caption": caption
                })
        app.config[f'MEDIA_CACHE'] = app.config.get('MEDIA_CACHE', {})
        for media in media_urls:
            app.config['MEDIA_CACHE'][media['id']] = media['original_url']
        return media_urls, caption, None
    except Exception as e:
        logger.error(f"Error fetching media from {post_url}: {e}")
        return [], "", f"Error: {str(e)}"

# Handle Bing Visual Search
def handle_consent(driver):
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "bnp_btn_accept")))
        accept_button = driver.find_element(By.ID, "bnp_btn_accept")
        accept_button.click()
        logger.info("✅ Bing cookie consent accepted")
    except Exception as e:
        logger.error(f"❌ Bing cookie consent not found: {e}")

def scroll_page(driver):
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def open_bing_with_image(image_url):
    driver = get_driver()
    driver.get("https://www.bing.com/visualsearch")
    time.sleep(3)

    handle_consent(driver)

    try:
        paste_area = driver.find_element(By.ID, "vsk_pastepn")
        paste_area.click()
        time.sleep(1)
        input_field = driver.find_element(By.ID, "vsk_imgpst")
        input_field.send_keys(image_url)
        input_field.send_keys(Keys.RETURN)
        logger.info("✅ Image URL pasted and search triggered")
    except Exception as e:
        logger.error(f"❌ Error pasting image URL: {e}")

    time.sleep(4)
    scroll_page(driver)

    image_data = []
    try:
        results = driver.find_elements(By.CSS_SELECTOR, ".expander_content li")
        for result in results:
            try:
                link_tag = result.find_element(By.CSS_SELECTOR, "a.richImgLnk")
                data_m = link_tag.get_attribute("data-m")
                data_m_json = json.loads(data_m)
                full_image_url = data_m_json.get("murl", "")

                img_tag = result.find_element(By.CSS_SELECTOR, "img")
                thumbnail_url = img_tag.get_attribute("src")
                alt = img_tag.get_attribute("alt")

                title = result.find_element(By.CSS_SELECTOR, ".tit").get_attribute("title") if result.find_elements(By.CSS_SELECTOR, ".tit") else "No title"
                domain = result.find_element(By.CSS_SELECTOR, ".domain").text if result.find_elements(By.CSS_SELECTOR, ".domain") else "No domain"

                image_data.append({"full_image_url": full_image_url, "thumbnail_url": thumbnail_url, "alt": alt, "title": title, "domain": domain})
            except Exception as e:
                logger.error(f"❌ Error extracting data: {e}")
    except Exception as e:
        logger.error(f"❌ Error extracting image data: {e}")

    driver.quit()
    return image_data

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    data = request.get_json()
    instagram_pages = data.get('instagram_pages', '').split(',')
    post_limit = data.get('post_limit', 10)
    if not instagram_pages or instagram_pages[0] == '':
        return jsonify({"error": "No Instagram pages provided"})
    results = scrape_instagram(instagram_pages, post_limit)
    return jsonify(results)

@app.route('/download', methods=['GET', 'POST'], endpoint='download_page')
def download_page():
    media_urls = []
    captions = []
    error = None
    post_urls = ""
    if request.method == 'POST':
        post_urls = request.form['post_url']
        post_url_list = post_urls.split(',')
        for post_url in post_url_list:
            post_url = post_url.strip()
            if post_url:
                media, caption, err = fetch_media(post_url)
                if err:
                    error = err
                    break
                media_urls.extend(media)
                captions.append(caption)
    return render_template('download.html', media_urls=media_urls, captions=captions, error=error, post_urls=post_urls)

@app.route('/preview/<string:media_id>/<string:media_type>')
def preview_media(media_id, media_type):
    try:
        media_cache = app.config.get('MEDIA_CACHE', {})
        if media_id not in media_cache:
            return "Media not found", 404
        original_url = media_cache[media_id]
        response = requests.get(original_url, stream=True)
        if media_type == 'video':
            return Response(response.iter_content(chunk_size=1024), content_type='video/mp4')
        else:
            return Response(response.iter_content(chunk_size=1024), content_type='image/jpeg')
    except Exception as e:
        logger.error(f"Error streaming media: {e}")
        return "Error streaming media", 500

@app.route('/download_media/<string:media_id>/<string:media_type>')
def download_media(media_id, media_type):
    try:
        media_cache = app.config.get('MEDIA_CACHE', {})
        if media_id not in media_cache:
            return "Media not found", 404
        original_url = media_cache[media_id]
        response = requests.get(original_url)
        if media_type == 'video':
            filename = f"instagram_video_{media_id}.mp4"
            content_type = 'video/mp4'
        else:
            filename = f"instagram_image_{media_id}.jpg"
            content_type = 'image/jpeg'
        return Response(io.BytesIO(response.content), mimetype=content_type, headers={"Content-Disposition": f"attachment;filename={filename}"})
    except Exception as e:
        logger.error(f"Error downloading media: {e}")
        return "Error downloading media", 500

@app.route('/edit_image', methods=['POST'])
def edit_image():
    image_url = request.json.get('image_url')
    image_id = request.json.get('image_id')
    image_data = open_bing_with_image(image_url)
    
    if not image_data:
        return jsonify({"error": "No results found for the image"}), 404
    
    app.config['MEDIA_CACHE'][image_id] = image_data[0]['full_image_url']
    
    return jsonify(image_data)

if __name__ == '__main__':
    app.run(debug=True)