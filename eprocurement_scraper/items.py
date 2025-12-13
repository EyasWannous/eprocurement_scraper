# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class EprocurementScraperItem(scrapy.Item):
    # define the fields for your item here like:
    # name = scrapy.Field()
    pass

class ProductItem(scrapy.Item):
    # Assignment-required fields
    brand = scrapy.Field()
    product_name = scrapy.Field()
    model_number = scrapy.Field()
    category = scrapy.Field()
    subcategory = scrapy.Field()
    technical_specs = scrapy.Field()
    short_description = scrapy.Field()
    long_description = scrapy.Field()
    product_image_url = scrapy.Field()
    datasheet_url = scrapy.Field()
    
    # For AI classification
    type_id = scrapy.Field()
    classification_path = scrapy.Field()
    
    # Utility fields
    source_url = scrapy.Field()
    scraped_timestamp = scrapy.Field()