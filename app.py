from flask import Flask, render_template, request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

app = Flask(__name__)

# Set up Selenium WebDriver
def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")  # Open in full screen
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Function to handle cookie consent pop-ups
def handle_consent(driver):
    # Handle Microsoft Bing cookie consent pop-up
    try:
        # Wait for the pop-up to appear
        time.sleep(2)  # Adjust timing if necessary
        # Click the "Accept" button
        accept_button = driver.find_element(By.ID, "bnp_btn_accept")
        accept_button.click()
        print("✅ Bing cookie consent accepted")
    except Exception as e:
        print(f"❌ Bing cookie consent not found or could not be clicked: {e}")

    # Handle other cookie consent pop-ups (if any)
    consent_button_xpaths = [
        "//button[contains(text(),'Allow all cookies')]",
        "//button[contains(text(),'Accept')]",
        "//button[contains(text(),'Consent')]",
        "//button[contains(text(),'Agree')]"
    ]

    for xpath in consent_button_xpaths:
        try:
            button = driver.find_element(By.XPATH, xpath)
            button.click()
            print("✅ Additional cookie consent accepted")
            time.sleep(1)
            break  # Exit loop if a button is found and clicked
        except:
            pass  # Continue if button is not found

# Function to open Bing Visual Search, handle consent, paste URL, press Enter, and click the Visual Search button
def open_bing_with_image(image_url):
    driver = get_driver()
    driver.get("https://www.bing.com/visualsearch")
    time.sleep(3)  # Wait for page to load

    # Handle cookie pop-ups
    handle_consent(driver)

    # Find the correct input field and paste image URL
    try:
        # Click on the paste area to activate the input field
        paste_area = driver.find_element(By.ID, "vsk_pastepn")
        paste_area.click()
        time.sleep(1)  # Wait for the input field to activate

        # Find the input field and paste the image URL
        input_field = driver.find_element(By.ID, "vsk_imgpst")
        input_field.send_keys(image_url)
        print("✅ Image URL pasted successfully")

        # Press Enter to trigger the search
        input_field.send_keys(Keys.RETURN)
        print("✅ Enter key pressed")
    except Exception as e:
        print(f"❌ Error pasting image URL or pressing Enter: {e}")

    # Wait for the Visual Search button to be clickable
    try:
        # Wait for the button to be clickable
        visual_search_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "div.action.vs.nofocus[title='Visual Search']"))
        )
        visual_search_button.click()
        print("✅ Visual Search button clicked")
    except Exception as e:
        print(f"❌ Error clicking Visual Search button: {e}")

    # Wait for the results to load
    time.sleep(4)  # Wait for 4 seconds to ensure the results are fully loaded

    # Extract all image data from the results
    image_data = []
    try:
        results = driver.find_elements(By.CSS_SELECTOR, ".expander_content li")
        for result in results:
            try:
                # Extract image URL
                img_tag = result.find_element(By.CSS_SELECTOR, "img")
                src = img_tag.get_attribute("src")
                alt = img_tag.get_attribute("alt")

                # Extract title (if available)
                title = result.find_element(By.CSS_SELECTOR, ".tit").get_attribute("title") if result.find_elements(By.CSS_SELECTOR, ".tit") else "No title"

                # Extract domain (if available)
                domain = result.find_element(By.CSS_SELECTOR, ".domain").text if result.find_elements(By.CSS_SELECTOR, ".domain") else "No domain"

                # Append the data to the list
                image_data.append({"src": src, "alt": alt, "title": title, "domain": domain})
            except Exception as e:
                print(f"❌ Error extracting data from a result: {e}")
    except Exception as e:
        print(f"❌ Error extracting image data: {e}")

    driver.quit()  # Close the browser
    return image_data

@app.route("/", methods=["GET", "POST"])
def index():
    image_data = []
    if request.method == "POST":
        image_url = request.form["image_url"]
        image_data = open_bing_with_image(image_url)
    return render_template("index.html", image_data=image_data)

if __name__ == "__main__":
    app.run(debug=True)