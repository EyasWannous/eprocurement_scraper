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
            
            r'sika-[a-z]+-\d+[a-z]?-\d+'
            r'sika-[a-z]+\d+[a-z]?'
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
        item['source_url'] = response.url

        # 1. Brand
        item['brand'] = 'Sika'
        
        # 2. Product Name - no fallbacks, just extract what's there
        name = response.css('h1::text').get() or response.css('title::text').get()
        item['product_name'] = self.clean_text(name) if name else ''
        
        # 3. Long Description - Enhanced fallback
        long_desc_val = response.css('meta[name="description"]::attr(content)').get()
        if not long_desc_val:
            # Fallback: First paragraph under H1 or Product Details
            first_p = response.css('.product-details p::text, .content p::text').get()
            if first_p:
                long_desc_val = first_p
        item['long_description'] = self.clean_text(long_desc_val) if long_desc_val else ''
        
        # 4. Short Description - no fallbacks
        paragraphs = response.css('p::text').getall()
        short_desc_paras = []
        for para in paragraphs[:5]:
            cleaned = self.clean_text(para)
            if cleaned and len(cleaned) > 50:
                short_desc_paras.append(cleaned)
        item['short_description'] = ' '.join(short_desc_paras)
        
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
        
        # 6. Datasheet URL - Enhanced
        datasheet_url = ''
        
        # Strategy 1: Look for explicit "Product Data Sheet" or "PDS" links
        # We look at text, title, and href for strong keywords
        pds_candidates = []
        
        # Get all links that might be PDFs
        all_pdf_links = response.css('a[href]')
        
        for link in all_pdf_links:
            href = link.attrib.get('href', '').strip()
            text = link.css('::text').get(default='').strip().lower()
            title = link.attrib.get('title', '').strip().lower()
            
            # Skip if not a likely file download or if it's a known non-PDS type
            if not href or href.startswith(('javascript:', '#', 'mailto:')):
                continue
                
            href_lower = href.lower()
            
            # Score the link
            score = 0
            is_pdf = href_lower.endswith('.pdf')
            
            # Strong indicators in text/title
            if 'product data sheet' in text or 'product data sheet' in title:
                score += 10
            if 'pds' in text.split() or 'pds' in title.split(): # specific word match
                score += 8
            if 'technical data sheet' in text or 'technical data sheet' in title:
                score += 8
            if 'tds' in text.split() or 'tds' in title.split():
                score += 6
                
            # Indicators in URL
            if 'pds' in href_lower:
                score += 5
            if 'data-sheet' in href_lower or 'datasheet' in href_lower:
                score += 4
                
            # Negative indicators (Safety Data Sheets, Brochures, etc)
            if 'safety' in text or 'sds' in text or 'msds' in text:
                score -= 20
            if 'safety' in title or 'sds' in title or 'msds' in title:
                score -= 20
            if 'safety' in href_lower or 'sds' in href_lower or 'msds' in href_lower:
                score -= 20
                
            if 'brochure' in text or 'brochure' in title or 'brochure' in href_lower:
                score -= 10
            if 'flyer' in text or 'flyer' in title or 'flyer' in href_lower:
                score -= 10
            if 'declaration' in text or 'dop' in text: # Declaration of Performance
                score -= 5
            
            # Penalize generic PDS pages
            if 'pds.html' in href_lower or 'documents-resources' in href_lower:
                score -= 30
                
            # Boost if it's a PDF
            if is_pdf:
                score += 20 # Increased from 2
            
            if score > 0:
                pds_candidates.append((score, urljoin(response.url, href)))
        
        # Sort candidates by score (descending)
        pds_candidates.sort(key=lambda x: x[0], reverse=True)
        
        if pds_candidates:
            datasheet_url = pds_candidates[0][1]
        
        # Strategy 2: Fallback - Look for any PDF in a "downloads" section if no strong candidate found
        if not datasheet_url:
            download_section = response.css('.downloads, .documents, .related-documents, #downloads')
            if download_section:
                potential_pdfs = download_section.css('a[href$=".pdf"]::attr(href)').getall()
                for pdf in potential_pdfs:
                    # Simple filter to avoid SDS
                    if 'sds' not in pdf.lower() and 'safety' not in pdf.lower():
                        datasheet_url = urljoin(response.url, pdf)
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
            # Look for explicit product codes: "Article No. 12345"
            article_match = re.search(r'(?:Article No\.|Product Code|Model No\.|Item No\.)\s*[:\s]*(\S+)', all_text, re.IGNORECASE)
            if article_match:
                # Prioritize this as it's more explicit
                model_number = article_match.group(1).strip()
                
            # Final cleanup and assignment
        if model_number:
            item['model_number'] = self.clean_text(model_number)
        else:
            # Fallback to cleaned product name
            product_name_parts = item.get('product_name', '').split()
            if product_name_parts:
                item['model_number'] = product_name_parts[0] # Assume first word is key identifier
            else:
                item['model_number'] = ''
            
        self.items_extracted += 1 
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