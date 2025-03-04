from flask import Flask, request, render_template, jsonify, Response, url_for, redirect
import pickle
import time
import json
import os
import uuid
import io
import re
import requests
import instaloader
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

app = Flask(__name__)
media_dir = 'media'
os.makedirs(media_dir, exist_ok=True)
L = instaloader.Instaloader()

def initialize_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def load_cookies(driver):
    try:
        driver.get("https://www.instagram.com/")
        time.sleep(3)
        if os.path.exists("cookies.pkl"):
            with open("cookies.pkl", "rb") as file:
                cookies = pickle.load(file)
            for cookie in cookies:
                driver.add_cookie(cookie)
            print("Cookies loaded successfully!")
            return True
        else:
            print("No saved cookies found! Please log in first.")
            return False
    except Exception as e:
        print(f"Error loading cookies: {e}")
        return False

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

def scrape_instagram(instagram_pages, post_limit=10):
    driver = initialize_driver()
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
        print(f"Scraping: {page}")
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

def fetch_media(post_url):
    try:
        shortcode = extract_shortcode(post_url)
        if not shortcode:
            return [], "Invalid URL format. Could not extract post shortcode from {post_url}", None
        print(f"Extracted shortcode: {shortcode}")
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
        print(f"Error fetching media from {post_url}: {e}")
        return [], "", f"Error: {str(e)}"

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

@app.route('/download', methods=['GET', 'POST'])
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
        print(f"Error streaming media: {e}")
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
        print(f"Error downloading media: {e}")
        return "Error downloading media", 500

if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Tools</title>
                    
<style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
        }
        h1, h2 {
            color: #405DE6;
            text-align: center;
        }
        .tools-container {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            justify-content: center;
            margin: 30px 0;
        }
        .tool-card {
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
            width: 45%;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        .tool-card:hover {
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transform: translateY(-5px);
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input, button {
            padding: 8px;
            width: 100%;
            box-sizing: border-box;
        }
        button {
            background-color: #405DE6;
            color: white;
            border: none;
            cursor: pointer;
            margin-top: 10px;
            border-radius: 4px;
            transition: background-color 0.3s;
        }
        button:hover {
            background-color: #2C3E8C;
        }
        .nav-tabs {
            display: flex;
            list-style: none;
            padding: 0;
            margin: 0 0 20px 0;
            border-bottom: 1px solid #ddd;
        }
        .nav-tabs li {
            padding: 10px 20px;
            cursor: pointer;
            margin-right: 5px;
            border: 1px solid transparent;
            border-radius: 4px 4px 0 0;
        }
        .nav-tabs li.active {
            border-color: #ddd;
            border-bottom-color: #fff;
            margin-bottom: -1px;
            font-weight: bold;
            color: #405DE6;
        }
        .tab-content {
            padding: 20px 0;
        }
        .tab-content .tab-pane {
            display: none;
        }
        .tab-content .tab-pane.active {
            display: block;
        }
        #results {
            margin-top: 20px;
            white-space: pre-wrap;
            background-color: #f5f5f5;
            padding: 15px;
            border-radius: 5px;
            max-height: 500px;
            overflow: auto;
            display: none;
        }
        .loading {
            text-align: center;
            display: none;
        }
        .post-results {
            margin-top: 20px;
            display: none;
        }
        .post-card {
            border: 1px solid #ddd;
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 5px;
            background-color: #f9f9f9;
        }
        .post-caption {
            margin-bottom: 10px;
            font-style: italic;
            color: #555;
        }
        .post-link {
            display: block;
            margin: 10px 0;
            color: #405DE6;
            text-decoration: none;
        }
        .post-link:hover {
            text-decoration: underline;
        }
        .download-btn {
            display: inline-block;
            margin-top: 10px;
            background-color: #405DE6;
            color: white;
            padding: 5px 10px;
            text-decoration: none;
            border-radius: 3px;
            font-size: 14px;
        }
        .download-btn:hover {
            background-color: #2C3E8C;
        }
    </style>
</head>
<body>
    <h1>Instagram Tools</h1>
    <ul class="nav-tabs">
        <li class="active" onclick="switchTab('scraper')">Profile Scraper</li>
        <li onclick="switchTab('downloader')">Media Downloader</li>
    </ul>
    <div class="tab-content">
        <div id="scraper" class="tab-pane active">
            <h2>Instagram Profile Scraper</h2>
            <div class="form-group">
                <label for="instagram-pages">Instagram Pages (separated by commas):</label>
                <input type="text" id="instagram-pages" placeholder="e.g., valorgi, hotfreestyle">
            </div>
            <div class="form-group">
                <label for="post-limit">Number of Posts to Scrape:</label>
                <input type="number" id="post-limit" value="10" min="1" max="50">
            </div>
            <button id="scrape-btn">Scrape Instagram Pages</button>
            <div class="loading" id="loading">
                <p>Scraping data, please wait...</p>
            </div>
            <div id="results"></div>
            <div id="post-results" class="post-results"></div>
            <button id="preview-all-btn" style="display: none; margin-top: 20px;">Preview All</button>
        </div>
        <div id="downloader" class="tab-pane">
            <h2>Instagram Media Downloader</h2>
            <form action="/download" method="POST">
                <div class="form-group">
                    <label for="post_url">Instagram Post URL(s):</label>
                    <input type="text" id="post_url" name="post_url" placeholder="https://www.instagram.com/p/XXXXXX/" required>
                </div>
                <button type="submit">Get Media</button>
            </form>
        </div>
    </div>
    <script>
        function switchTab(tabId) {
            document.querySelectorAll('.tab-pane').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.nav-tabs li').forEach(tab => tab.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            document.querySelector(`.nav-tabs li[onclick="switchTab('${tabId}')"]`).classList.add('active');
        }
        document.getElementById('scrape-btn').addEventListener('click', async function() {
            const instagramPages = document.getElementById('instagram-pages').value;
            const postLimit = document.getElementById('post-limit').value;
            if (!instagramPages) {
                alert('Please enter at least one Instagram page');
                return;
            }
            const loading = document.getElementById('loading');
            const results = document.getElementById('results');
            const postResults = document.getElementById('post-results');
            const previewAllBtn = document.getElementById('preview-all-btn');
            loading.style.display = 'block';
            results.style.display = 'none';
            postResults.style.display = 'none';
            postResults.innerHTML = '';
            previewAllBtn.style.display = 'none';
            try {
                const response = await fetch('/scrape', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({instagram_pages: instagramPages, post_limit: postLimit}),
                });
                const data = await response.json();
                results.textContent = JSON.stringify(data, null, 2);
                let hasValidPosts = false;
                const postUrls = [];
                for (const [page, posts] of Object.entries(data)) {
                    if (Array.isArray(posts) && posts.length > 0) {
                        hasValidPosts = true;
                        const pageHeader = document.createElement('h3');
                        pageHeader.textContent = `Posts from ${page}`;
                        postResults.appendChild(pageHeader);
                        posts.forEach(post => {
                            const postCard = document.createElement('div');
                            postCard.className = 'post-card';
                            const caption = document.createElement('div');
                            caption.className = 'post-caption';
                            caption.textContent = post.caption;
                            const link = document.createElement('a');
                            link.className = 'post-link';
                            link.href = post.post_url;
                            link.textContent = post.post_url;
                            link.target = '_blank';
                            postCard.appendChild(caption);
                            postCard.appendChild(link);
                            postResults.appendChild(postCard);
                            if (post.post_url && post.post_url !== "No URL") {
                                postUrls.push(post.post_url);
                            }
                        });
                    }
                }
                if (hasValidPosts) {
                    postResults.style.display = 'block';
                    previewAllBtn.style.display = 'block';
                    previewAllBtn.addEventListener('click', () => {
                        const downloadTab = document.getElementById('downloader');
                        const postUrlInput = downloadTab.querySelector('#post_url');
                        postUrlInput.value = postUrls.join(',');
                        switchTab('downloader');
                        downloadTab.querySelector('form').submit();
                    });
                } else {
                    const noPostsMessage = document.createElement('p');
                    noPostsMessage.textContent = 'No posts found or error occurred.';
                    postResults.appendChild(noPostsMessage);
                    postResults.style.display = 'block';
                }
            } catch (error) {
                results.textContent = 'Error: ' + error.message;
                results.style.display = 'block';
            } finally {
                loading.style.display = 'none';
            }
        });
    </script>
</body>
</html>
        ''')
    with open('templates/download.html', 'w', encoding='utf-8') as f:
        f.write('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Media Downloader</title>
                
<style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
        }
        h1, h2 {
            color: #405DE6;
            text-align: center;
        }
        .form-group {
            margin-bottom: 15px;
        }
        input[type="text"] {
            width: 70%;
            padding: 8px;
            margin-right: 10px;
        }
        button {
            padding: 8px 15px;
            background-color: #405DE6;
            color: white;
            border: none;
            cursor: pointer;
            border-radius: 4px;
        }
        button:hover {
            background-color: #2C3E8C;
        }
        .media-container {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin-top: 20px;
        }
        .media-item {
            border: 1px solid #ddd;
            padding: 15px;
            border-radius: 5px;
            width: 320px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .media-item img, .media-item video {
            width: 100%;
            height: auto;
            display: block;
            margin-bottom: 10px;
        }
        .download-btn {
            display: block;
            text-align: center;
            background-color: #405DE6;
            color: white;
            padding: 8px;
            text-decoration: none;
            border-radius: 3px;
            margin-top: 10px;
        }
        .download-btn:hover {
            background-color: #2C3E8C;
        }
        .error {
            color: red;
            margin: 10px 0;
            padding: 10px;
            background-color: #ffeeee;
            border-radius: 5px;
        }
        .media-count {
            margin: 10px 0;
            color: #666;
        }
        .media-number {
            margin-bottom: 8px;
            font-weight: bold;
        }
        .loading {
            text-align: center;
            margin: 20px 0;
            font-style: italic;
            color: #666;
        }
        .back-link {
            display: inline-block;
            margin: 20px 0;
            color: #405DE6;
            text-decoration: none;
        }
        .back-link:hover {
            text-decoration: underline;
        }
        .post-caption {
            margin: 20px 0;
            padding: 15px;
            background-color: #f9f9f9;
            border-left: 4px solid #405DE6;
            font-style: italic;
        }
    </style>
</head>
<body>
    <h1>Instagram Media Downloader</h1>
    <a href="/" class="back-link">← Back to Home</a>
    <form method="POST">
        <div class="form-group">
            <label for="post_url">Instagram Post URL(s):</label>
            <input type="text" id="post_url" name="post_url" value="{{ post_urls }}" placeholder="https://www.instagram.com/p/XXXXXX/" required>
            <button type="submit">Get Media</button>
        </div>
    </form>
    {% if error %}
        <div class="error">{{ error }}</div>
    {% endif %}
    {% if media_urls %}
        <h2>Media Preview</h2>
        <div class="media-count">Found {{ media_urls|length }} media item{% if media_urls|length > 1 %}s{% endif %}</div>
        <div class="media-container">
            {% for media in media_urls %}
                <div class="media-item">
                    <div class="media-number">Item {{ loop.index }} of {{ media_urls|length }}</div>
                    {% if media.type == 'image' %}
                        <img src="{{ media.preview_url }}" alt="Instagram Image" loading="lazy">
                    {% elif media.type == 'video' %}
                        <video controls preload="metadata">
                            <source src="{{ media.preview_url }}" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                    {% endif %}
                    <div class="caption">{{ media.caption }}</div>
                    <a href="{{ url_for('download_media', media_id=media.id, media_type=media.type) }}" class="download-btn">Download {{ media.type|capitalize }}</a>
                </div>
            {% endfor %}
        </div>
    {% endif %}
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const videos = document.querySelectorAll('video');
            videos.forEach(video => {
                video.addEventListener('loadstart', function() {
                    this.setAttribute('poster', 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 100 100"><text x="50%" y="50%" font-size="14" text-anchor="middle" alignment-baseline="middle" font-family="Arial, sans-serif">Loading video...</text></svg>');
                });
            });
        });
    </script>
</body>
</html>
        ''')
    app.run(debug=True)