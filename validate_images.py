import pandas as pd
import requests
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

def validate_url(url):
    """Checks if a URL is reachable and returns 200 OK."""
    if not url or pd.isna(url):
        return False, "Missing URL"
    
    try:
        # Use HEAD request for speed
        response = requests.head(url, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            return True, "OK"
        # Fallback to GET if HEAD fails (some servers block HEAD)
        elif response.status_code == 405:
            response = requests.get(url, timeout=5, stream=True)
            if response.status_code == 200:
                return True, "OK"
        return False, f"Status {response.status_code}"
    except requests.RequestException as e:
        return False, str(e)

def validate_images(input_file, output_file=None):
    print(f"Reading {input_file}...")
    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    if 'product_image_url' not in df.columns:
        print("Error: 'product_image_url' column not found.")
        return

    print(f"Validating {len(df)} images...")
    
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_idx = {executor.submit(validate_url, row['product_image_url']): idx for idx, row in df.iterrows()}
        
        for future in tqdm(as_completed(future_to_idx), total=len(df)):
            idx = future_to_idx[future]
            is_valid, reason = future.result()
            results.append((idx, is_valid, reason))

    # Sort results by index to maintain order
    results.sort(key=lambda x: x[0])
    
    # Add columns to DataFrame
    df['image_valid'] = [r[1] for r in results]
    df['image_status'] = [r[2] for r in results]

    # Statistics
    valid_count = df['image_valid'].sum()
    print(f"\nValidation Complete:")
    print(f"✓ Valid: {valid_count}")
    print(f"✗ Invalid: {len(df) - valid_count}")
    print(f"Success Rate: {(valid_count/len(df))*100:.1f}%")

    if output_file:
        df.to_csv(output_file, index=False)
        print(f"\nSaved report to {output_file}")
    else:
        # Print invalid ones
        invalid_df = df[~df['image_valid']]
        if not invalid_df.empty:
            print("\nInvalid Images Sample:")
            print(invalid_df[['product_name', 'product_image_url', 'image_status']].head())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate image URLs in a CSV file")
    parser.add_argument("input_file", help="Path to input CSV file")
    parser.add_argument("-o", "--output", help="Path to output CSV file with validation results")
    
    args = parser.parse_args()
    validate_images(args.input_file, args.output)
