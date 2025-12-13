"""
Classify products from existing CSV files.
Useful for testing classification without re-scraping.
"""

import sys
import pandas as pd
from pathlib import Path
from eprocurement_scraper.classifier import get_classifier


def classify_csv(input_file, output_file=None, limit=None, start=0, end=None):
    """
    Classify products from a CSV file.
    
    Args:
        input_file: Path to input CSV file
        output_file: Path to output CSV (default: adds _classified suffix)
        limit: Max number of products to classify
        start: Starting row index (0-based)
        end: Ending row index (exclusive)
    """
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)
    print(f"Found {len(df)} products")
    
    # apply row selection
    if end is not None:
        df = df.iloc[start:end]
        print(f"Processing rows {start} to {end-1} ({len(df)} products)")
    elif limit is not None:
        df = df.iloc[start:start+limit]
        print(f"Processing {len(df)} products starting from row {start}")
        df = df.iloc[start:]
        print(f"Processing from row {start} onwards ({len(df)} products)")
    
    # init classifier
    classifier = get_classifier()
    classifier.load()
    
    # classify each product
    print("\nClassifying products...")
    results = []
    
    for idx, row in df.iterrows():
        product_name = row.get('product_name', 'Unknown')
        # handle NaN values
        if pd.isna(product_name):
            product_name = 'Unknown'
        
        print(f"[{idx+1}/{len(df)}] {str(product_name)[:40]}...")
        
        try:
            # convert row to dict and handle NaN values
            product_dict = row.to_dict()
            # replace NaN with empty strings
            for key, value in product_dict.items():
                if pd.isna(value):
                    product_dict[key] = ''
            
            result = classifier.classify(product_dict, use_llm=True, top_k=10)
            
            if result:
                row['type_id'] = result['id']
                row['classification_path'] = result.get('classification_path', '')
                row['classification_name'] = result.get('name', '')
                row['classification_reasoning'] = result.get('llm_reasoning', '')
                row['confidence_score'] = result.get('confidence_score', '')
                print(f"  → {result['name']} (ID: {result['id']})")
            else:
                row['type_id'] = None
                row['classification_path'] = ''
                print("  → No classification")
        
        except Exception as e:
            print(f"  → Error: {e}")
            row['type_id'] = None
            row['classification_path'] = ''
        
        results.append(row)
    
    # save results
    result_df = pd.DataFrame(results)
    
    # ensure columns are in a nice order
    cols = ['brand', 'product_name', 'type_id', 'classification_path', 'classification_name', 'confidence_score', 'classification_reasoning']
    remaining_cols = [c for c in result_df.columns if c not in cols]
    result_df = result_df[cols + remaining_cols]
    
    if output_file is None:
        # auto-generate output filename
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_classified.csv"
    
    result_df.to_csv(output_file, index=False)
    print(f"\n✓ Saved to {output_file}")
    print(f"Classified {len(result_df)} products")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Classify products from CSV file')
    parser.add_argument('input', help='Input CSV file path')
    parser.add_argument('-o', '--output', help='Output CSV file path')
    parser.add_argument('-l', '--limit', type=int, help='Number of products to classify')
    parser.add_argument('-s', '--start', type=int, default=0, help='Starting row (0-based)')
    parser.add_argument('-e', '--end', type=int, help='Ending row (exclusive)')
    
    args = parser.parse_args()
    
    classify_csv(
        input_file=args.input,
        output_file=args.output,
        limit=args.limit,
        start=args.start,
        end=args.end
    )


if __name__ == '__main__':
    main()
