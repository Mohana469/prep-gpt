import os
import traceback
from PyPDF2 import PdfReader
from django.conf import settings as config
import shutil

from PIL import Image, ImageDraw, ImageFont
import textwrap

import json
from dotenv import load_dotenv  
from googleapiclient.discovery import build  
import requests
import time
from selenium import webdriver
from bs4 import BeautifulSoup


# Simple cleaning for this specific task(To be impoved upon)
def clean_text(text):
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        if line.strip().isdigit():
            continue
        if any(
            keyword in line.upper()
            for keyword in [
                "CHAPTER",
                "PHYSICS",
                "MECHANICAL PROPERTIES",
                "REPRINT",
                "SUMMARY",
                "POINTS TO PONDER",
                "EXERCISES",
                "==START OF OCR",
                "==END OF OCR",
            ]
        ):
            if not any(
                keyword in line.upper()
                for keyword in [
                    "INTRODUCTION",
                    "STRESS",
                    "HOOK",
                    "CURVE",
                    "MODULI",
                    "APPLICATIONS",
                    "POISSON",
                    "8.1",
                    "8.2",
                    "8.3",
                    "8.4",
                    "8.5",
                    "8.6",
                ]
            ):
                continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)



def convert_pdf_to_text_util(pdf_file):
    if pdf_file is None:
        return "Please upload a PDF file.", None

    try:
        os.makedirs(config.PDF_TEMP_DIR, exist_ok=True)
        pdf_path = pdf_file.name
        file_name = os.path.basename(pdf_path)
        base_name, _ = os.path.splitext(file_name)
        output_text_path = os.path.join(config.PDF_TEMP_DIR, f"{base_name}.txt")

        print(f"Converting PDF: {pdf_path} to {output_text_path}")
        text = ""
        with open(pdf_path, "rb") as f:
            reader = PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        if not text.strip():
            print("Extracted text is empty or only whitespace.")
            return (
                "Error: Could not extract text from the PDF. It might be an image-based PDF without OCR.",
                None,
            )

        with open(output_text_path, "w", encoding="utf-8") as f:
            f.write(text)

        print(f"Successfully converted PDF to text: {output_text_path}")
        return (
            f"Successfully converted '{file_name}' to text. Text file saved temporarily as '{os.path.basename(output_text_path)}'.",
            output_text_path,
        )

    except Exception as e:
        error_message = f"Error during PDF conversion: {e}\n{traceback.format_exc()}"
        print(error_message)
        return f"An error occurred during conversion: {e}", None

def images_to_pdf(image_files, output_pdf):
    # Open the first image and convert to RGB (required for PDF)
    first_image = Image.open(image_files[0]).convert('RGB')
    
    # Open the rest of the images and convert to RGB
    images = [Image.open(img).convert('RGB') for img in image_files[1:]]
    
    # Save all images into one PDF file
    first_image.save(output_pdf, save_all=True, append_images=images, quality=100, optimize=False)


def render_text_pdf_format(text: str, output_path: str, FONT_PATH: str,):
    # Settings
    A4_WIDTH, A4_HEIGHT = 794, 1123
    LINE_SPACING = 46
    MARGIN = 25
    FONT_SIZE = 28
    LINES_PER_PAGE = (A4_HEIGHT - 2 * MARGIN) // LINE_SPACING

    # Input text
    # Prepare output folder
    os.makedirs("pages", exist_ok=True)

    # Font
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    # Wrap and split text
    # --- Preserve line breaks and wrap long lines ---
    raw_lines = text.splitlines()
    lines = []
    for line in raw_lines:
        if line.strip() == "":
            lines.append("")  # keep blank lines
        else:
            wrapped = textwrap.wrap(line, width=70)
            lines.extend(wrapped)

    pages = []
    for i in range(0, len(lines), LINES_PER_PAGE):
        pages.append(lines[i:i + LINES_PER_PAGE])

    # Create pages
    for i, page_lines in enumerate(pages):
        img = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), "white")
        draw = ImageDraw.Draw(img)

        # Draw notebook lines
        for y in range(MARGIN, A4_HEIGHT - MARGIN, LINE_SPACING):
            draw.line((MARGIN, y, A4_WIDTH - MARGIN, y), fill=(200, 230, 255), width=1)

        # Draw red margin line
        draw.line((MARGIN, MARGIN, MARGIN, A4_HEIGHT - MARGIN), fill=(255, 100, 100), width=2) #right
        draw.line((A4_WIDTH - MARGIN, MARGIN, A4_WIDTH - MARGIN, A4_HEIGHT - MARGIN), fill=(255, 100, 100), width=2) #left

        # Write text
        y = MARGIN
        for line in page_lines:
            draw.text((MARGIN+10, y+15), line, font=font, fill=(0, 0, 255))
            y += LINE_SPACING

        img.save(f"pages/page_{i+1}.png")

    print(f"{len(pages)} clean handwritten-style A4 pages saved in 'pages/' folder.")

    # Example usage:
    images_in_folder = os.listdir("pages")
    image_list = []
    for i in range(len(images_in_folder)):
        image_name = f"pages/page_{i+1}.png"
        image_list.append(image_name)

    images_to_pdf(image_list, output_path)
    if os.path.exists('pages'):
        shutil.rmtree('pages')
        print(f"Deleted folder: pages")
    else:
        print("Folder does not exist")

def _google_custom_search_raw(query: str, num_results: int = 5):
    load_dotenv()  

    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")

    if not api_key or not cse_id:
        return "Error: GOOGLE_API_KEY or GOOGLE_CSE_ID not found in .env file. Google Custom Search is disabled."

    try:
        service = build("customsearch", "v1", developerKey=api_key)

        res = service.cse().list(q=query, cx=cse_id, num=num_results).execute()
        if "items" in res and res["items"]:
            data = {}
            for i, item in enumerate(res["items"]):
                title = item.get("title", "N/A")
                link = item.get("link", "N/A")
                # Send an HTTP GET request to the URL
                response = requests.get(link)
                # Parse the content using BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                # Extract visible text
                if len(soup.get_text()) > 700:
                    text = soup.get_text()
                else:
                    #if text is not extractable using requests
                    driver = webdriver.Chrome()
                    driver.get(link)
                    # Wait for JS to load
                    time.sleep(5)
                    # Get the page source after JS loads
                    html = driver.page_source
                    # Parse with BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    text = soup.get_text()
                    driver.quit()
                data[title] = ' '.join(text.split())
            # for k, v in data.items():
            #     print(f"Key: {k}\n Value: {v}\n")
            return data
        else:
            return "No relevant search results found."

    except Exception as e:
        return f"An error occurred during Google Custom Search: {e}. Ensure API key and CSE ID are correct and billing is enabled."


def google_custom_search_tool_wrapper(query: str) -> str:
    return _google_custom_search_raw(
        query, num_results=5
    )