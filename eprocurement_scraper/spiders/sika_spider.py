import scrapy
import re
import json
from urllib.parse import urljoin, urlparse
from ..items import ProductItem


class SikaSpider(scrapy.Spider):
    name = 'sika'
    allowed_domains = ['gcc.sika.com']
    
    custom_settings = {
        'ROBOTSTXT_OBEY': False,
        'DOWNLOAD_DELAY': 1.0,  # Reduced slightly for faster crawling
        'CONCURRENT_REQUESTS': 8, # Increased for better throughput
        'RETRY_ENABLED': True,
        'RETRY_TIMES': 2,
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
        'https://gcc.sika.com/en/construction.html', # Main entry point
        'https://gcc.sika.com/en/construction/concrete.html',
        'https://gcc.sika.com/en/construction/waterproofing.html',
        'https://gcc.sika.com/en/construction/flooring.html',
        'https://gcc.sika.com/en/construction/sealing-bonding.html',
        'https://gcc.sika.com/en/construction/refurbishment.html',
        'https://gcc.sika.com/en/construction/roofing.html',
        'https://gcc.sika.com/en/construction/industry.html',
        'https://gcc.sika.com/en/construction/flooring-and-coating.html',
        'https://gcc.sika.com/en/construction/sealing-bonding/sealing-bonding-solutions.html',
        'https://gcc.sika.com/en/construction/refurbishment/wall-facade-system.html',
        'https://gcc.sika.com/en/construction/building-finishing/tiling-system.html'
    ]
    
    visited_urls = set()
    processed_products = set()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items_extracted = 0
    
    def parse(self, response):
        """Extract product links and subcategory links recursively"""
        current_url = response.url.strip()
        
        if current_url in self.visited_urls:
            return
        
        self.visited_urls.add(current_url)
        self.logger.info(f"🔍 Scanning {response.url} - Status: {response.status}")
        
        # Get all links from the page
        all_links = response.css('a::attr(href)').getall()
        
        product_links = []
        category_links = []
        
        for link in all_links:
            if not link or link.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                continue
            
            link = link.strip()
            full_url = urljoin(response.url, link)
            parsed_url = urlparse(full_url)
            
            # Skip external domains
            if parsed_url.netloc not in ['gcc.sika.com', 'www.gcc.sika.com', '']:
                continue
            
            # Skip non-product/non-category pages
            if self.is_non_product_url(link):
                continue
            
            # Check if it's a product
            if self.is_likely_product(link):
                if full_url not in self.processed_products:
                    product_links.append(full_url)
            else:
                # If not a product and not a "bad" URL, treat as potential category
                # Only follow links within the construction section or similar relevant sections
                if '/en/construction' in full_url or '/en/industry' in full_url:
                    if full_url not in self.visited_urls:
                        category_links.append(full_url)
        
        # Remove duplicates
        product_links = list(set(product_links))
        category_links = list(set(category_links))
        
        self.logger.info(f"✅ Found {len(product_links)} products and {len(category_links)} potential categories on {response.url}")
        
        # Process product links
        for link in product_links:
            if link not in self.processed_products:
                self.logger.info(f"📦 Processing product: {link}")
                self.processed_products.add(link)
                yield scrapy.Request(link, callback=self.parse_product)
                
        # Process category links (Recursive)
        for link in category_links:
            if link not in self.visited_urls:
                yield scrapy.Request(link, callback=self.parse)
    
    def is_non_product_url(self, url):
        """Check if URL is definitely not a product page or useful category"""
        url_lower = url.lower()
        non_product_patterns = [
            'mbcc-product-integration', 'about-', 'contact-', 'news', 'media',
            'sustainability', 'career', 'investor', 'sika-gcc', 'who-we-are',
            'organization', 'target-markets', 'group-management', 'history',
            'compliance', 'purpose', 'values', 'brand', 'strategy', 'acquisition',
            'mbcc', 'document-basket', 'favorite-products', 'search', 'sitemap',
            'legal', 'privacy', 'cookies', 'terms', 'login', 'register', 'my-sika',
            'brochure', 'software', 'application', 'calculator', 'design',
            'knowledge-center', 'bim-hub', 'project-references', 'overview',
            'solutions', 'systems', 'en.sitemap.xml', 'gcc.sitemap-seo.xml',
            'download', 'pdf', 'jpg', 'png'
        ]
        return any(pattern in url_lower for pattern in non_product_patterns)
    
    def is_likely_product(self, link):
        """Enhanced product detection - look for product patterns"""
        link = link.lower().strip()
        
        # Must be HTML page
        if not link.endswith(('.html', '.htm')):
            return False
        
        # Skip obvious non-product pages
        if self.is_non_product_url(link):
            return False
        
        # Extract last part of URL
        last_part = link.split('/')[-1].lower()
        
        # Product patterns
        product_patterns = [
            r'sika[-a-z]*-[a-z]{1,3}-\d+',           # sika-sigunit-sa-160
            r'sikafiber[-a-z]*-\d+',                 # sikafiber-12, sikafiber-142
            r'sikatard[-a-z]*-\d+',                  # sikatard-hca-10
            r'sikarapid[-a-z]*-\d+',                 # sikarapid-ac-555
            r'sikacontrol[-a-z]*-\d+',               # sikacontrol-3760wt
            r'sikacrete[-a-z]*-\d+',                 # sikacrete-3701
            r'sika-\d+',                             # sika-1
            r'sika-4a',                              # sika-4a
            r'sigunit[-_]([a-z]{1,3}-\d+)',          # sigunit-sa-430
            r'[a-z]+-\d+[a-z]?\.(html|htm)',         # product-123.html
            r'sikaseal[-a-z]*-\d+',                  # sikaseal-490-sl

            # Add these patterns to your product_patterns list:
            r'sikaflex[-a-z]*-\d+',               # sikaflex-2c-ns-ezmix
            r'sikarep[-a-z]*-\d+',                # sikarep-mc-80, sikarep-fine-sa
            r'sikarep-[a-z]+',                    # sikarep-n, sikarep-nf, sikarep-sa
            r'sikatop[-a-z]*-\d+',                # sikatop-armatec-110epocem
            r'sikaemaco[-a-z]*-\d+',              # sikaemaco-n-105, sikaemaco-s-422
            r'sika-ucrete[-a-z]*-\d+',            # sika-ucrete-cr-460, sika-ucrete-p-460
            r'sika-intraplast[-a-z]*',            # sika-intraplast-cfg
            r'sikabond[-a-z]*',                   # sikabond-dv
            r'sikalatex',                         # sikalatex (standalone)
            r'intracrete[-a-z]*-\d+',             # intracrete-eh-v-ae

            r'sika-injection[-a-z]*-\d+',         # sika-injection-101rc
            r'sikaswell[-a-z]*',                  # sikaswell-a-ae
            r'sika-carbodur[-a-z]*',              # sika-carbodur-s
            r'sika-dust[-a-z]*',                  # sika-dust-seal-sa

            r'sika-cni[-a-z]*',                   # sika-cni-om, sika-cni-k
            r'sika-mould[-a-z]*',                 # sika-mould-ba
            r'sikalite[-a-z]*',                   # sikalite-ae
            r'sika-antisol[-a-z]*',               # sika-antisol-wb
            r'sikagard[-a-z0-9]*',                # sikagard-550-w-elasticg, sikagard-520-w, sikagard-pw-ae

            # Waterproofing products
            r'sikalastic[-a-z0-9]*',              # sikalastic-wr, sikalastic-311-ae, sikalastic-841-st, sikalastic-152-sa
            r'sika-igolflex[-a-z0-9]*',           # sika-igolflex-ae, sika-igolflex-365gcc
            r'sikadur[-a-z0-9]*',                 # sikadur-52-lp, sikadur-52-lp-ae, sikadur-combiflexsgsystem
            r'sikainject[-a-z0-9]*',              # sikainject-201-de, sikainject-107-de, sikainject-216-de, sikainject-304-de
            r'sikaplan[-a-z0-9]*',                # sikaplan-wp-tapesystem, sikaplan-wp-controlsocket6, sikaplan-wp-disc
            r'sikaproof[-a-z0-9]*',               # sikaproof-tape-a, sikaproof-sandwichtape, sikaproof-adhesive-03ae
            r'sika-monotop[-a-z0-9]*',            # sika-monotop-108waterplugae, sika-monotop-615hsfsa, sika-monotop-hsf
            r'sikashield[-a-z0-9]*',              # sikashield-p26-mgsa4mm, sikashield-pb-p15pesa4mm, sikashield-e55-pesa15mm

            # Concrete admixtures
            r'sika-stabilizer[-a-z0-9]*',         # sika-stabilizer-312mbf
            r'sika-rugasol[-a-z0-9]*',            # sika-rugasol-2-liquid
            r'sika-separol[-a-z0-9]*',            # sika-separol-320ws
            r'sikacem[-a-z0-9]*',                 # sikacem-100-mp

            # Refurbishment products
            r'sikawrap[-a-z0-9]*',                # sikawrap-230-c, sikawrap-600-c-wv
            r'sika-ferrogard[-a-z0-9]*',          # sika-ferrogard-903plus, sika-ferrogard-710reba, sika-ferrogard-500crete
            
            # Sealing & Bonding products
            r'sika-boom[-a-z0-9]*',               # sika-boom-s, sika-boom-115-flameresistant
            r'sikasil[-a-z0-9]*',                 # sikasil-719-ws, sikasil-403-fire
            r'sikahyflex[-a-z0-9]*',              # sikahyflex-300-eu
        ]
        
        for pattern in product_patterns:
            if re.search(pattern, last_part):
                return True
        
        # Check if it's a deep URL (likely a product page)
        # Increased depth check to avoid categories being mistaken
        if link.count('/') >= 6 and ('construction' in link or 'concrete' in link or 'waterproofing' in link):
            return True
        
        return False
    
    def parse_product(self, response):
        """Parse product page - extract data without validation"""
        self.logger.info(f"🔧 Parsing product page: {response.url}")
        
        # [NEW] Validate if it's a real product page
        if not self.is_valid_product_page(response):
            self.logger.warning(f"⚠️ Skipping non-product page: {response.url}")
            return

        item = ProductItem()
        
        # 1. Brand
        item['brand'] = 'Sika'
        
        # 2. Product Name - no fallbacks, just extract what's there
        name = response.css('h1::text').get() or response.css('title::text').get()
        item['product_name'] = self.clean_text(name) if name else ''
        
        # 3. Short Description - Enhanced fallback
        short_desc = response.css('meta[name="description"]::attr(content)').get()
        if not short_desc:
            # Fallback: First paragraph under H1 or Product Details
            first_p = response.css('.product-details p::text, .content p::text').get()
            if first_p:
                short_desc = first_p
        item['short_description'] = self.clean_text(short_desc) if short_desc else ''
        
        # 4. Long Description - no fallbacks
        paragraphs = response.css('p::text').getall()
        meaningful_paras = []
        for para in paragraphs[:5]:
            cleaned = self.clean_text(para)
            if cleaned and len(cleaned) > 50:
                meaningful_paras.append(cleaned)
        item['long_description'] = ' '.join(meaningful_paras)
        
        # 5. Technical Specs - Enhanced (Tables + Headers)
        specs = {}
        # 5a. Tables
        tables = response.css('table')
        for table_idx, table in enumerate(tables):
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
        
        # 5b. H3 Headers (Iterative approach)
        target_keys = ['composition', 'shelf life', 'storage conditions', 'density', 'ph-value', 'viscosity', 'color', 'colour', 'packaging', 'total chloride ion content']
        
        h3s = response.css('h3')
        for h3 in h3s:
            header_text = h3.css('::text').get(default='').strip().lower()
            if any(k in header_text for k in target_keys):
                key_clean = re.sub(r'[^\w\s-]', '', header_text).strip().lower().replace(' ', '_')
                
                # Get following content until next header
                values = h3.xpath('./following-sibling::node()').getall()
                collected_text = []
                for v in values:
                    # Check if it's a header tag
                    if re.match(r'<h\d', v, re.IGNORECASE):
                        break
                    # Remove tags to check for text
                    text_only = re.sub(r'<[^>]+>', '', v).strip()
                    if text_only:
                        collected_text.append(text_only)
                    if len(collected_text) >= 2: # Limit to 2 paragraphs
                        break
                
                if collected_text:
                    specs[key_clean] = ' '.join(collected_text)

        item['technical_specs'] = json.dumps(specs) if specs else ''
        
        # 6. Datasheet URL - Improved
        datasheet_url = ''
        pdf_links = response.css('a[href$=".pdf"]')
        for link in pdf_links:
            link_text = link.css('::text').get(default='').lower()
            href = link.attrib.get('href', '')
            if 'data sheet' in link_text or 'pds' in link_text or 'product data' in link_text:
                datasheet_url = urljoin(response.url, href)
                break
        
        if not datasheet_url:
            pdf_hrefs = response.css('a[href*=".pdf"]::attr(href)').getall()
            for link in pdf_hrefs:
                if 'pds-' in link.lower() or 'data-sheet' in link.lower() or 'datasheet' in link.lower():
                    datasheet_url = urljoin(response.url, link)
                    break
        item['datasheet_url'] = datasheet_url
        
        # 7. Model Number - Enhanced
        model_number = ''
        url = response.url.lower()
        
        # Try specific patterns first (including short models)
        model_match = re.search(r'sika[-a-z]*-([a-z]{0,3}-?\d+[a-z]?)', url.split('/')[-1])
        if model_match:
            model_number = model_match.group(1).upper()
        
        if not model_number:
            # Try from page text
            all_text = ' '.join(response.css('body ::text').getall())
            # Look for "Article No. 12345"
            article_match = re.search(r'(?:Article|Product)\s*(?:No\.?|Number)\s*:?\s*(\d+)', all_text, re.IGNORECASE)
            if article_match:
                model_number = article_match.group(1)
            else:
                # Look for patterns like "Sika-1" in title
                text_match = re.search(r'Sika[®™]?\s*([A-Z0-9-]{2,10})', item['product_name'])
                if text_match:
                     candidate = text_match.group(1)
                     if any(c.isdigit() for c in candidate):
                         model_number = candidate
        
        # Fallback: Look in specs
        if not model_number and specs:
            for key, val in specs.items():
                if 'article' in key or 'product no' in key or 'model' in key:
                    model_number = val
                    break

        item['model_number'] = model_number
        
        # 8. Product Image - Improved
        image_url = ''
        image_url = response.css('meta[property="og:image"]::attr(content)').get()
        
        if not image_url:
            img_src = response.css('.product-image img::attr(src)').get() or response.css('.main-image img::attr(src)').get()
            if img_src:
                image_url = urljoin(response.url, img_src)

        if not image_url and model_number:
            model_clean = model_number.lower().replace('-', '')
            if len(model_clean) >= 2:
                image_url = f"https://sika.scene7.com/is/image/sika/{model_clean}"
        item['product_image_url'] = image_url
        
        # 9. Source URL
        item['source_url'] = response.url
        
        # 10. Category/Subcategory from URL
        item['category'] = ''
        item['subcategory'] = ''
        
        if 'gcc.sika.com/en/' in response.url:
            path_segments = response.url.split('gcc.sika.com/en/')[-1].split('/')
            if len(path_segments) > 1:
                clean_segments = [s for s in path_segments[:-1] if s.lower() not in ['construction', 'en']]
                if len(clean_segments) > 0:
                    item['category'] = clean_segments[0].replace('-', ' ').title()
                if len(clean_segments) > 1:
                    item['subcategory'] = clean_segments[1].replace('-', ' ').title()
        
        if not item['category']:
            breadcrumbs = response.css('.breadcrumb li a::text, .breadcrumbs li a::text, ol.breadcrumb li a::text').getall()
            breadcrumbs = [b.strip() for b in breadcrumbs if b.strip()]
            filtered_crumbs = [b for b in breadcrumbs if b.lower() not in ['home', 'construction', 'sika gcc']]
            if len(filtered_crumbs) > 0:
                item['category'] = filtered_crumbs[0]
            if len(filtered_crumbs) > 1:
                item['subcategory'] = filtered_crumbs[1]

        item['type_id'] = ''
        item['classification_path'] = ''
        
        self.items_extracted += 1
        self.logger.info(f"✅ [{self.items_extracted}] Extracted: {item['product_name']} (Model: {item['model_number']})")
        yield item
    
    def is_valid_product_page(self, response):
        """Check if the page is a valid product page"""
        # Check for specific headers that appear on product pages
        headers = response.xpath('//h1 | //h2 | //h3').css('::text').getall()
        header_text = ' '.join(headers).lower()
        
        # Stricter requirements: Must have "Product Details" or "Technical Data"
        # "Application" alone is not enough as category pages have "Application Examples"
        strong_indicators = ['product details', 'technical data', 'technical information']
        if any(term in header_text for term in strong_indicators):
            return True
            
        # Check for PDS link - must be a specific product data sheet
        links = response.css('a[href*=".pdf"]::attr(href)').getall()
        if any('pds' in l.lower() or 'data-sheet' in l.lower() for l in links):
            # Double check it's not just a brochure
            if not any('brochure' in l.lower() for l in links):
                return True
            
        return False
    
    def clean_text(self, text):
        """Clean text without fallbacks"""
        if not text:
            return ''
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def closed(self, reason):
        """Called when spider is closed"""
        self.logger.info(f"🏁 Spider closed. Reason: {reason}")
        self.logger.info(f"📊 Total items extracted: {self.items_extracted}")
        self.logger.info(f"🌐 Total pages visited: {len(self.visited_urls)}")
        self.logger.info(f"✅ Total unique products processed: {len(self.processed_products)}")