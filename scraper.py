"""
scaper.py
--------------------
Batch-crawls a list of documentation URLs in parallel using Crawl4AI's arun_many and a memory-adaptive dispatcher.
Tracks memory usage, prints a summary of successes/failures, and is suitable for large-scale doc scraping jobs.
Usage: Call main() or run as a script. Adjust max_concurrent for parallelism.
"""
import os
import sys
import psutil
import asyncio
import requests
from typing import List
from xml.etree import ElementTree
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, MemoryAdaptiveDispatcher

async def crawl_parallel(urls: List[str], output_dir: str = "crawled_data", max_concurrent: int = 10):
    """
    Crawls a list of URLs in parallel, saving the content of each successful crawl
    to a specified output directory.

    Args:
        urls (List[str]): A list of URLs to crawl.
        output_dir (str): The directory where crawled data will be saved.
        max_concurrent (int): The maximum number of concurrent browser sessions.
    """
    print("\n=== Parallel Crawling with arun_many + Dispatcher ===")

    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    print(f"Saving crawled data to: {os.path.abspath(output_dir)}")

    # Track the peak memory usage for observability
    peak_memory = 0
    process = psutil.Process(os.getpid())
    def log_memory(prefix: str = ""):
        nonlocal peak_memory
        current_mem = process.memory_info().rss  # in bytes
        if current_mem > peak_memory:
            peak_memory = current_mem
        print(f"{prefix} Current Memory: {current_mem // (1024 * 1024)} MB, Peak: {peak_memory // (1024 * 1024)} MB")

    # Configure the browser for headless operation and resource limits
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
    )
    # Set up crawl config and dispatcher for batch crawling
    crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=70.0,  # Don't exceed 70% memory usage
        check_interval=1.0,            # Check memory every second
        max_session_permit=max_concurrent  # Max parallel browser sessions
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        log_memory("Before crawl: ")
        # arun_many handles all URLs in parallel, batching and resource management handled by dispatcher
        results = await crawler.arun_many(
            urls=urls,
            config=crawl_config,
            dispatcher=dispatcher
        )
        success_count = 0
        fail_count = 0
        # Loop through all crawl results and tally success/failure
        for result in results:
            if result.success:
                success_count += 1
                try:
                    # Create a safe filename from the URL
                    # Replace non-alphanumeric characters with underscores
                    # and limit length to avoid issues
                    filename = result.url.replace("https://", "").replace("http://", "").replace("/", "_").replace("?", "_").replace("=", "_").replace("&", "_")
                    filename = filename.replace("www.", "")
                    # Ensure filename is not too long or empty
                    if not filename:
                        filename = "index"
                    filename = filename[:200] + ".html" # Limit filename length
                    file_path = os.path.join(output_dir, filename)

                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(result.content)
                    print(f"Saved: {result.url} to {file_path}")
                except Exception as e:
                    print(f"Error saving content for {result.url}: {e}")
                    fail_count += 1 # Count as a failure if saving fails
            else:
                print(f"Error crawling {result.url}: {result.error_message}")
                fail_count += 1

        print(f"\nSummary:")
        print(f"  - Successfully crawled: {success_count}")
        print(f"  - Failed: {fail_count}")
        log_memory("After crawl: ")
        print(f"\nPeak memory usage (MB): {peak_memory // (1024 * 1024)}")

def get_docs_urls():
    """
    Fetches all URLs from the Mosdac website.
    Uses the sitemap (https://www.mosdac.gov.in/sitemap.xml) to get these URLs.

    Returns:
        List[str]: List of URLs
    """
    sitemap_url = "https://www.mosdac.gov.in/sitemap.xml"
    try:
        response = requests.get(sitemap_url)
        response.raise_for_status()

        # Parse the XML
        root = ElementTree.fromstring(response.content)

        # Extract all URLs from the sitemap
        # The namespace is usually defined in the root element
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [loc.text for loc in root.findall('.//ns:loc', namespace)]

        return urls
    except Exception as e:
        print(f"Error fetching sitemap: {e}")
        return []

async def main():
    urls = get_docs_urls()
    if urls:
        print(f"Found {len(urls)} URLs to crawl")
        # Call crawl_parallel with the new output_dir argument
        await crawl_parallel(urls, output_dir="crawled_mosdac_data", max_concurrent=10)
    else:
        print("No URLs found to crawl")

if __name__ == "__main__":
    asyncio.run(main())