# eProcurement Product Scraper & Classifier

An intelligent web scraping system that automatically extracts product information from brand websites and classifies them using AI-powered taxonomy matching.

## 🌟 Features

- **Multi-Brand Spiders**: Pre-configured spiders for Sika, Flex, and more
- **Automatic Classification**: AI-powered product classification using FAISS vector search + Gemini LLM
- **Smart Data Cleaning**: Removes whitespace, parses technical specs, normalizes text
- **Vector Database Caching**: Fast index loading (~2s vs ~30s rebuild)
- **Production Ready**: Configurable pipelines, error handling, and logging

## 📋 Requirements

- Python 3.8+
- Google Gemini API key (for LLM classification)

## 🚀 Installation

1. **Clone the repository**

```bash
git clone git@github.com:EyasWannous/eprocurement_scraper.git
cd eprocurement_scraper
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Configure LLM Provider**

```bash
# Create .env file
cp .env.example .env

# Choose your LLM provider (gemini or groq)
LLM_PROVIDER=gemini  # or groq

# For Gemini:
GEMINI_API_KEY=your_api_key_here

# For Groq (Llama):
GROQ_API_KEY=your_api_key_here
```

**Get API Keys:**

- Gemini: https://makersuite.google.com/app/apikey
- Groq: https://console.groq.com/keys (free tier available!)

## 🎯 Quick Start

### Test with 10 Products

```bash
scrapy crawl sika -s CLOSESPIDER_ITEMCOUNT=10 -o test_output.csv
```

### Run Full Spider

```bash
scrapy crawl sika -o output/sika_products.csv
```

### Available Spiders

```bash
# List all available spiders
scrapy list

# Run specific spiders
scrapy crawl flex
scrapy crawl sika
```

## 📁 Project Structure

```
eprocurement_scraper/
├── eprocurement_scraper/
│   ├── spiders/           # Spider definitions (sika.py, flex.py, etc.)
│   ├── classifier.py      # AI classification module
│   ├── pipelines.py       # Data processing pipelines
│   ├── settings.py        # Scrapy configuration
│   └── items.py           # Data item definitions
├── .cache/                # Vector database cache (auto-generated)
├── output/                # Output CSV files (gitignored)
├── classification_tree.csv # Product taxonomy
├── pipeline.py            # Standalone classification testing
├── requirements.txt       # Python dependencies
└── .env                   # API keys (gitignored)
```

## 🔧 Configuration

### Switch LLM Provider

Choose between Gemini (Google) or Groq (Llama) in `.env`:

```bash
# Use Gemini (default)
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key

# Or use Groq (faster, generous free tier)
LLM_PROVIDER=groq
GROQ_API_KEY=your_key
```

**Groq Benefits:**

- Faster inference (~2-3x speed)
- Generous free tier
- Llama 3.3 70B model

### Disable Classification

In `eprocurement_scraper/pipelines.py`:

```python
class ClassificationPipeline:
    def __init__(self):
        self.enabled = False  # Disable classification
```

### Adjust Number of Candidates

In `eprocurement_scraper/classifier.py`:

```python
self.top_k = 10  # Number of categories to send to LLM
```

### Custom Output Path

```bash
scrapy crawl sika -o custom_folder/my_products.csv
```

## 📊 Output Format

CSV files include:

| Column                  | Description                         |
| ----------------------- | ----------------------------------- |
| `brand`               | Product brand                       |
| `product_name`        | Product name                        |
| `category`            | Classification category            |
| `subcategory`         | Website subcategory                 |
| `technical_specs`     | JSON technical specifications       |
| `short_description`   | Brief description                   |
| `long_description`    | Detailed description                |
| `type_id`             | **AI-classified category ID** |
| `classification_path` | **Taxonomy path**             |
| `scraped_timestamp`   | When scraped                        |

## 🧪 Testing

### Classify Existing CSV Data

```bash
# Classify first 10 products from sika_products.csv
python classify_csv.py output/sika_products.csv -l 10

# Classify products from row 100 to 110
python classify_csv.py output/sika_products.csv -s 100 -e 110

# Classify 5 products starting from row 50
python classify_csv.py output/flex_tools_products.csv -s 50 -l 5

# Specify custom output file
python classify_csv.py output/sika_products.csv -l 10 -o test_classification.csv
```

### Test Without Classification

```bash
scrapy crawl sika -s CLOSESPIDER_ITEMCOUNT=10 \
  -s ITEM_PIPELINES="{'eprocurement_scraper.pipelines.DataCleaningPipeline': 100}" \
  -o test_no_classification.csv
```

### Test Specific Spider Limits

```bash
# Stop after 50 items
scrapy crawl flex -s CLOSESPIDER_ITEMCOUNT=50 -o flex_50.csv

# Set timeout (seconds)
scrapy crawl sika -s CLOSESPIDER_TIMEOUT=300 -o sika_5min.csv
```

## 🔍 How Classification Works

1. **Spider scrapes** product data from website
2. **DataCleaningPipeline** (order 100):
   - Cleans text fields
   - Parses technical specs JSON
   - Adds timestamp
3. **ClassificationPipeline** (order 200):
   - Loads FAISS vector index (once per run)
   - Embeds product using sentence-transformers
   - Retrieves top 10 candidates via vector search
   - **LLM (Gemini)** selects best match
   - Adds `type_id` and `classification_path`
4. **Save to CSV**

## 📝 Creating New Spiders

```bash
# Generate spider template
scrapy genspider newbrand example.com

# Edit eprocurement_scraper/spiders/newbrand.py
# Implement parse methods to extract product data
```

## 🐛 Troubleshooting

### Classification Errors

- Check `.env` has valid `GEMINI_API_KEY`
- Ensure `classification_tree.csv` exists
- Review logs for specific error messages

### Slow Performance

- First run builds cache (~30s) - subsequent runs are fast
- Disable LLM for bulk scraping if needed
- Use `CLOSESPIDER_ITEMCOUNT` for testing

### Cache Issues

```bash
# Clear cache to rebuild
rm -rf .cache
```

## 📚 Commands Reference

```bash
# List spiders
scrapy list

# Run with item limit
scrapy crawl <spider> -s CLOSESPIDER_ITEMCOUNT=<N>

# Custom output file
scrapy crawl <spider> -o <path>

# View settings
scrapy settings --get ITEM_PIPELINES

# Shell for debugging
scrapy shell <url>
```

## 🤝 Contributing

1. Add new spiders in `eprocurement_scraper/spiders/`
2. Follow existing spider patterns
3. Test with small limits first
4. Update README with new spiders

## 📄 License

[Your License Here]

## 🙏 Acknowledgments

- **Scrapy**: Web scraping framework
- **FAISS**: Vector similarity search
- **Sentence Transformers**: Text embeddings
- **Google Gemini**: LLM for classification
