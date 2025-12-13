import scrapy
import re
import json
from urllib.parse import urljoin, urlparse
from ..items import ProductItem


class FlexToolsSpider(scrapy.Spider):
    name = 'flex_tools'
    allowed_domains = ['www.flex-tools.com']
    
    custom_settings = {
        'ROBOTSTXT_OBEY': True,
        'DOWNLOAD_DELAY': 1.5,
        'CONCURRENT_REQUESTS': 4,
        'RETRY_ENABLED': True,
        'RETRY_TIMES': 3,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 1,
        'AUTOTHROTTLE_MAX_DELAY': 10,
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'LOG_LEVEL': 'INFO',
        'FEED_EXPORT_ENCODING': 'utf-8',
        # Remove this limit for production
        # 'CLOSESPIDER_ITEMCOUNT': 10,
    }
    
    start_urls = [
        'https://www.flex-tools.com/en/products',
        'https://www.flex-tools.com/en/accessories',
        # 'https://www.flex-tools.com/en/accessories/accessories-for-metal-surface-finishing/dummy-tk-l'
    ]
    
    visited_urls = set()
    processed_products = set()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items_extracted = 0
    
    def parse(self, response):
        """Handle the main entry points and recursive crawling"""
        self.logger.info(f"🔍 Scanning {response.url}")
        
        # 1. Check if this is a product page
        if self.is_product_page(response):
            yield from self.parse_product(response)
            return

        # 2. If not a product page, it's likely a category/listing page
        # Extract all card links which represent categories or products
        card_links = response.css('a.card-link::attr(href)').getall()
        
        self.logger.info(f"Found {len(card_links)} card links on {response.url}")
        
        for link in card_links:
            full_url = urljoin(response.url, link)
            if full_url not in self.visited_urls:
                self.visited_urls.add(full_url)
                yield scrapy.Request(full_url, callback=self.parse)
        
        # Handle pagination if present
        next_page = response.css('a.next::attr(href), .pagination-next a::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

    def is_product_page(self, response):
        """Check if the current page is a product page"""
        # Indicators of a product page:
        # 1. Presence of "Technical Data" or "Specifications"
        has_tech_specs = response.css('.technical-data, .specifications, h3:contains("Technical attributes")').get()
        
        # 2. Presence of "Buy" buttons or similar
        has_buy_button = response.css('button:contains("Buy"), a:contains("Buy")').get()
        
        # 3. Structure: Has H1 but NO product-card-grid (which implies it's a leaf node)
        has_h1 = response.css('h1').get()
        has_sub_grid = response.css('.product-card-grid').get()
        
        # 4. URL pattern check (fallback)
        url = response.url.lower()
        is_product_url = re.search(r'/(?:products|accessories)/[\w-]+/[\w-]+', url) and not has_sub_grid
        
        self.logger.info(f"🕵️ Detection for {url}: H1={bool(has_h1)}, Grid={bool(has_sub_grid)}, Specs={bool(has_tech_specs)}, Buy={bool(has_buy_button)}, URL_Match={bool(is_product_url)}")

        if has_h1 and not has_sub_grid:
             return True
             
        if has_tech_specs:
            return True
            
        if is_product_url:
            return True
            
        return False
    
    def parse_product(self, response):
        """Parse individual product page"""
        if response.url in self.processed_products:
            return
        
        self.logger.info(f"🔧 Parsing product page: {response.url}")
        item = ProductItem()
        
        # 1. Brand (always Flex for this domain)
        item['brand'] = 'Flex'
        
        # 2. Product Name
        name_selectors = [
            'h1.product-title::text',
            'h1.title::text',
            '.product-name h1::text',
            '.product-title::text',
            'h1::text',
            'title::text'
        ]
        
        product_name = ''
        for selector in name_selectors:
            name = response.css(selector).get()
            if name and name.strip():
                product_name = name.strip()
                break
        
        item['product_name'] = self.clean_text(product_name) if product_name else ''
        
        # 3. Short Description
        short_desc_selectors = [
            'meta[name="description"]::attr(content)',
            '.short-description p::text',
            '.product-short-description p::text',
            '.summary p::text',
            '.excerpt p::text'
        ]
        
        short_desc = ''
        for selector in short_desc_selectors:
            desc = response.css(selector).get()
            if desc and desc.strip():
                short_desc = desc.strip()
                break
        
        # Fallback: First paragraph from product description
        if not short_desc:
            first_para = response.css('.product-description p::text, .description p::text').get()
            if first_para:
                short_desc = first_para[:200] + '...' if len(first_para) > 200 else first_para
        
        item['short_description'] = self.clean_text(short_desc) if short_desc else ''
        
        # 4. Long Description
        long_description = ''
        
        # Try specific description containers first
        description_selectors = [
            '.product-info-description', # Specific to Flex
            '.product-description', 
            '.long-description', 
            '.description',
            '.product-info', # Fallback
            '.tab-description',
            '.text-paragraph-content .content'
            # Removed .product-details as it contains buttons/UI elements
        ]
        
        for selector in description_selectors:
            desc_content = response.css(f'{selector}').get()
            if desc_content:
                # Remove scripts, styles and unnecessary elements
                desc_content = re.sub(r'<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>', '', desc_content, flags=re.DOTALL)
                desc_content = re.sub(r'<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>', '', desc_content, flags=re.DOTALL)
                desc_content = re.sub(r'<[^>]+>', '', desc_content)  # Remove all HTML tags
                long_description = self.clean_text(desc_content)
                break
        
        # If no structured description found, get paragraphs
        if not long_description:
            paragraphs = response.css('p::text').getall()
            meaningful_paras = []
            for para in paragraphs[:8]:  # First 8 paragraphs
                cleaned = self.clean_text(para)
                if cleaned and len(cleaned) > 50 and not any(skip in cleaned.lower() for skip in ['cookie', 'privacy', 'terms', 'contact', 'sitemap', 'copyright', 'local dealer', 'standard supply']):
                    meaningful_paras.append(cleaned)
                    if len(meaningful_paras) >= 3:  # Limit to 3 meaningful paragraphs
                        break
            long_description = ' '.join(meaningful_paras)
        
        # Clean up common noise from description
        noise_phrases = [
            'Local dealers', 'Standard supply', 'Select product version', 
            'Versions available', 'Downloads', 'Instruction manual', 
            'Spare part drawing', 'Product data sheet'
        ]
        for phrase in noise_phrases:
            long_description = long_description.replace(phrase, '')
            
        item['long_description'] = self.clean_text(long_description)
        
        # 5. Technical Specifications
        specs = {}
        
        # Method 1: Parse specification tables
        tables = response.css('table.spec-table, table.technical-data, table.product-attributes, table.data-table')
        for table in tables:
            rows = table.css('tr')
            for row in rows:
                cells = row.css('td, th')
                if len(cells) >= 2:
                    key = cells[0].css('::text').get(default='').strip()
                    value = cells[1].css('::text').get(default='').strip()
                    if key and value and len(key) > 2 and len(value) > 2:
                        key_clean = re.sub(r'[^\w\s-]', '', key).strip().lower()
                        value_clean = self.clean_text(value)
                        if key_clean and value_clean:
                            specs[key_clean] = value_clean
        
        # Method 2: Look for specification lists
        if not specs:
            spec_items = response.css('.specifications li, .tech-specs li, .product-specs li')
            for item in spec_items:
                text = item.css('::text').get(default='').strip()
                if ':' in text:
                    key, value = text.split(':', 1)
                    key_clean = re.sub(r'[^\w\s-]', '', key).strip().lower()
                    value_clean = self.clean_text(value)
                    if key_clean and value_clean:
                        specs[key_clean] = value_clean
                        
        # Method 3: Parse from text content if structured data missing
        if not specs:
            # Look for "Technical data" section and parse following text
            tech_section = response.xpath('//*[contains(text(), "Technical data")]/following::text()').getall()
            current_key = None
            for text in tech_section[:20]: # Limit lookahead
                text = text.strip()
                if not text or text in ['Downloads', 'Instruction manual']: continue
                
                # Heuristic: Key is usually text, Value often has numbers
                if not current_key and not any(c.isdigit() for c in text):
                    current_key = text
                elif current_key:
                    key_clean = re.sub(r'[^\w\s-]', '', current_key).strip().lower()
                    specs[key_clean] = text
                    current_key = None

        item['technical_specs'] = json.dumps(specs) if specs else ''
        
        # 6. Datasheet URL
        datasheet_url = ''
        
        # Look for PDF links with specific text
        pdf_links = response.css('a[href$=".pdf"]')
        for link in pdf_links:
            link_text = link.css('::text').get(default='').lower()
            href = link.attrib.get('href', '')
            if any(term in link_text for term in ['datasheet', 'data sheet', 'manual', 'specification', 'technical']):
                datasheet_url = urljoin(response.url, href)
                break
        
        # Fallback: look for any PDF with product name
        if not datasheet_url:
            pdf_hrefs = response.css('a[href*=".pdf"]::attr(href)').getall()
            for link in pdf_hrefs:
                if 'manual' in link.lower() or 'datasheet' in link.lower() or 'spec' in link.lower():
                    datasheet_url = urljoin(response.url, link)
                    break
        
        item['datasheet_url'] = datasheet_url
        
        # 7. Model Number
        model_number = ''
        
        # Strategy 1: Extract from Product Name (Most reliable for Flex)
        # e.g. "GPS 35 18-EC - FLEX" -> "GPS 35 18-EC"
        name_match = re.match(r'^([A-Z0-9\s/-]+?)(?:\s+-\s+FLEX)?$', item['product_name'])
        if name_match:
            candidate = name_match.group(1).strip()
            # Verify it looks like a model number (has digits)
            if any(c.isdigit() for c in candidate):
                model_number = candidate
        
        # Strategy 2: Extract from URL (last segment)
        if not model_number:
            url = response.url.lower()
            slug = url.split('/')[-1]
            if any(c.isdigit() for c in slug):
                model_number = slug.upper().replace('-', ' ')
        
        # Strategy 3: Look in specifications
        if not model_number and specs:
            for key, value in specs.items():
                if any(term in key for term in ['model', 'ref', 'article', 'item', 'part', 'order no']):
                    model_number = value
                    break
        
        item['model_number'] = model_number
        
        # 8. Product Image URL
        image_url = ''
        
        # Strategy 1: Open Graph image
        image_url = response.css('meta[property="og:image"]::attr(content)').get() or response.css('meta[name="og:image"]::attr(content)').get()
        
        # Strategy 2: Main product image
        if not image_url:
            img_selectors = [
                '.product-image img::attr(src)',
                '.main-image img::attr(src)',
                '.woocommerce-main-image img::attr(src)',
                '.gallery-image img::attr(src)',
                'img.product-photo::attr(src)'
            ]
            
            for selector in img_selectors:
                img_src = response.css(selector).get()
                if img_src:
                    image_url = urljoin(response.url, img_src)
                    break
        
        # Strategy 3: First large image on the page
        if not image_url:
            images = response.css('img::attr(src)').getall()
            for img in images:
                if 'logo' not in img.lower() and 'icon' not in img.lower() and 'sprite' not in img.lower():
                    image_url = urljoin(response.url, img)
                    break
        
        item['product_image_url'] = image_url
        
        # 9. Source URL
        item['source_url'] = response.url
        
        # 10. Category and Subcategory (based on URL structure)
        item['category'] = ''
        item['subcategory'] = ''
        
        if '/products/' in response.url:
            item['category'] = 'Products'
            # Extract subcategory from URL
            path_parts = response.url.split('/')
            for i, part in enumerate(path_parts):
                if part == 'products' and i + 1 < len(path_parts):
                    if path_parts[i + 1] and not path_parts[i + 1].startswith('product-'):
                        item['subcategory'] = path_parts[i + 1].replace('-', ' ').title()
        elif '/accessories/' in response.url:
            item['category'] = 'Accessories'
            # Extract subcategory from URL
            path_parts = response.url.split('/')
            for i, part in enumerate(path_parts):
                if part == 'accessories' and i + 1 < len(path_parts):
                    if path_parts[i + 1] and not path_parts[i + 1].startswith('accessory-'):
                        item['subcategory'] = path_parts[i + 1].replace('-', ' ').title()
        
        # Fallback: Use breadcrumbs
        if not item['category']:
            breadcrumbs = response.css('.breadcrumb li a::text, .breadcrumbs li a::text, ol.breadcrumb li a::text').getall()
            breadcrumbs = [b.strip() for b in breadcrumbs if b.strip()]
            filtered_crumbs = [b for b in breadcrumbs if b.lower() not in ['home', 'flex-tools.com', '']]
            if len(filtered_crumbs) > 0:
                item['category'] = filtered_crumbs[0]
            if len(filtered_crumbs) > 1:
                item['subcategory'] = filtered_crumbs[1]
        
        # 11. Classification fields (will be filled by pipeline)
        item['type_id'] = ''
        item['classification_path'] = ''
        
        # Check for variants table (e.g. accessories with different sizes)
        variants_table = response.css('.accessory-variants-table, .product-variants-table')
        if variants_table:
            self.logger.info(f"🔢 Found variants table for {item['product_name']}")
            
            # Extract headers to map columns
            headers = variants_table.css('thead th::text').getall()
            headers = [h.strip() for h in headers if h.strip()]
            
            # Iterate over rows
            rows = variants_table.css('tbody tr.row-variant')
            for row in rows:
                # Clone the base item
                variant_item = item.copy()
                
                # Extract Order Number (usually the first column or specifically marked)
                order_number = row.css('.column-article-number::text').get()
                if not order_number:
                    # Fallback to first cell
                    order_number = row.css('td:nth-child(2)::text').get() # 2nd child because 1st is opener button
                
                if order_number:
                    variant_item['model_number'] = order_number.strip()
                
                # Extract other variant specs
                variant_specs = specs.copy() if specs else {}
                cells = row.css('td')
                
                # Map cells to headers (skipping opener column if present)
                # Adjust index based on table structure. Usually first col is opener.
                cell_texts = [c.css('::text').get(default='').strip() for c in cells]
                
                # Simple heuristic mapping
                for i, text in enumerate(cell_texts):
                    if text and i < len(headers) + 1: # +1 for opener offset
                        # Try to match with header
                        header_idx = i - 1 # Assuming first col is opener
                        if 0 <= header_idx < len(headers):
                            key = headers[header_idx]
                            if key.lower() not in ['order number', 'article number']:
                                variant_specs[key] = text
                
                variant_item['technical_specs'] = json.dumps(variant_specs)
                
                # Append variant info to name to make it unique
                # e.g. "Collet (3mm)"
                discriminator = []
                for k, v in variant_specs.items():
                    if any(x in k.lower() for x in ['diameter', 'size', 'dimension', 'type']):
                        discriminator.append(v)
                
                if discriminator:
                    variant_item['product_name'] = f"{item['product_name']} ({', '.join(discriminator)})"
                
                self.items_extracted += 1
                self.logger.info(f"✅ [{self.items_extracted}] Extracted Variant: {variant_item['product_name']} (Model: {variant_item['model_number']})")
                yield variant_item
                
        else:
            # No variants table, yield single item
            self.items_extracted += 1
            self.logger.info(f"✅ [{self.items_extracted}] Extracted: {item['product_name']} (Model: {item['model_number']})")
            self.processed_products.add(response.url)
            yield item
    
    def clean_text(self, text):
        """Clean text - remove HTML, extra spaces, etc."""
        if not text:
            return ''
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove JavaScript code blocks
        text = re.sub(r'<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>', '', text, flags=re.DOTALL)
        
        # Remove style blocks
        text = re.sub(r'<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>', '', text, flags=re.DOTALL)
        
        # Remove comments
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        
        # Remove special characters but keep important punctuation
        text = re.sub(r'[^\w\s.,;:()\-+@#%$€£¥&*°\'"/\\]', '', text)
        
        # Remove multiple spaces and newlines
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def closed(self, reason):
        """Called when spider is closed"""
        self.logger.info(f"🏁 Spider closed. Reason: {reason}")
        self.logger.info(f"📊 Total items extracted: {self.items_extracted}")
        self.logger.info(f"🌐 Total pages visited: {len(self.visited_urls)}")
        self.logger.info(f"✅ Total unique products processed: {len(self.processed_products)}")