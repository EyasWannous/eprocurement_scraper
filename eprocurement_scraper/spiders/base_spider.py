import scrapy
from eprocurement_scraper.items import ProductItem
from datetime import datetime

class BaseProductSpider(scrapy.Spider):
    """Base spider with shared logic for all product sites."""
    
    custom_settings = {
        'DOWNLOAD_DELAY': 1,
        'FEED_EXPORT_FIELDS': [  # Define CSV column order
            'brand', 'product_name', 'model_number', 'category', 
            'subcategory', 'technical_specs', 'short_description',
            'long_description', 'product_image_url', 'datasheet_url',
            'type_id', 'classification_path', 'source_url'
        ],
    }
    
    def parse_product(self, response):
        """Override this method in each child spider with site-specific selectors."""
        raise NotImplementedError("Please implement parse_product in child spider")
        
    def start_requests(self):
        """Start from the start_urls defined in each child spider."""
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse)
            
    def parse(self, response):
        """
        Find all product links on a category page and schedule them for parsing.
        Child spiders should override to define how to find product links.
        """
        # EXAMPLE: Find product links - YOU MUST CUSTOMIZE PER SITE
        product_links = response.css('a.product-link::attr(href)').getall()
        
        for link in product_links:
            absolute_url = response.urljoin(link)
            yield scrapy.Request(absolute_url, callback=self.parse_product)
        
        # Handle pagination if exists
        next_page = response.css('a.next-page::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)
            
    def create_item(self, response, **kwargs):
        """Helper to create a pre-populated ProductItem."""
        item = ProductItem()
        item['source_url'] = response.url
        item['scraped_timestamp'] = datetime.now().isoformat()
        
        # Set keyword arguments (like brand)
        for key, value in kwargs.items():
            if key in item.fields:
                item[key] = value
                
        return item