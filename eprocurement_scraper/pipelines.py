# Scrapy pipelines
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

from itemadapter import ItemAdapter
import json
from datetime import datetime


class EprocurementScraperPipeline:
    def process_item(self, item, spider):
        return item


class DataCleaningPipeline:
    """Cleans and validates scraped data"""
    
    def process_item(self, item, spider):
        item['scraped_timestamp'] = datetime.now().isoformat()
        
        # clean up text fields
        text_fields = ['product_name', 'short_description', 'long_description']
        for field in text_fields:
            if field in item:
                item[field] = self._clean_text(item[field])
        
        # parse technical specs JSON if needed
        if 'technical_specs' in item and isinstance(item['technical_specs'], str):
            try:
                specs = json.loads(item['technical_specs'])
                item['technical_specs'] = json.dumps(specs, ensure_ascii=False)
            except:
                pass
        
        return item
    
    def _clean_text(self, text):
        if not text:
            return ''
        text = ' '.join(text.split())
        return text.strip()


class ClassificationPipeline:
    """Classifies products using vector search + LLM"""
    
    def __init__(self):
        self.classifier = None
        self.enabled = True  # set to False to disable
    
    def open_spider(self, spider):
        if not self.enabled:
            spider.logger.info("[Classification] Pipeline disabled")
            return
        
        try:
            from .classifier import get_classifier
            self.classifier = get_classifier()
            self.classifier.load()
            spider.logger.info("[Classification] ✓ Classifier ready")
        except Exception as e:
            spider.logger.error(f"[Classification] Failed to initialize: {e}")
            self.enabled = False
    
    def process_item(self, item, spider):
        if not self.enabled or self.classifier is None:
            return item
        
        try:
            result = self.classifier.classify(dict(item), use_llm=True, top_k=10)
            
            if result:
                item['type_id'] = result['id']
                item['classification_path'] = result.get('classification_path', '')
                item['category'] = result['name'] # [NEW] Map classification name to category
                spider.logger.info(
                    f"[Classification] {item.get('product_name', 'Unknown')[:30]}... "
                    f"→ {result['name']} (ID: {result['id']})"
                )
            else:
                spider.logger.warning(f"[Classification] No result for {item.get('product_name', 'Unknown')}")
        
        except Exception as e:
            spider.logger.error(f"[Classification] Error: {e}")
        
        return item
    
    def close_spider(self, spider):
        if self.enabled:
            spider.logger.info("[Classification] Pipeline closed")