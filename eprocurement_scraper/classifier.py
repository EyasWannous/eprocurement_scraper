"""
Product classification module using vector search and LLM.
Supports both Gemini and Groq (Llama) via environment variables.
"""

import os
import json
from pathlib import Path
import pandas as pd
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Gemini support
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# Groq support
try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False


class ProductClassifier:
    """Handles product classification with FAISS + Gemini/Groq."""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        load_dotenv()
        
        self.csv_path = 'classification_tree.csv'
        self.model_name = 'all-MiniLM-L6-v2'
        self.top_k = 10
        
        # LLM configuration
        self.llm_provider = os.getenv('LLM_PROVIDER', 'gemini').lower()
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        self.groq_api_key = os.getenv('GROQ_API_KEY')
        
        self.cache_dir = Path('.cache')
        self.cache_dir.mkdir(exist_ok=True)
        self.index_cache = self.cache_dir / 'faiss_index.bin'
        self.df_cache = self.cache_dir / 'taxonomy_df.pkl'
        
        self.index = None
        self.model = None
        self.df = None
        self.llm_client = None
        self.llm_model_name = None
        
        # initialize based on provider
        if self.llm_provider == 'groq' and HAS_GROQ and self.groq_api_key:
            self.llm_client = Groq(api_key=self.groq_api_key)
            self.llm_model_name = 'llama-3.3-70b-versatile'  # fast and capable
            print(f"[Classifier] Using Groq ({self.llm_model_name})")
        elif self.llm_provider == 'gemini' and HAS_GENAI and self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)  # type: ignore
            self.llm_client = genai.GenerativeModel('gemini-2.0-flash')  # type: ignore
            self.llm_model_name = 'gemini-2.0-flash'
            print(f"[Classifier] Using Gemini ({self.llm_model_name})")
        else:
            print(f"[Classifier] No LLM configured (provider: {self.llm_provider})")
        
        self._initialized = True
    
    def load(self, force_rebuild=False):
        if self.index is not None and not force_rebuild:
            return
        
        # try loading from cache first
        if not force_rebuild and self.df_cache.exists():
            print("[Classifier] Loading cached taxonomy...")
            self.df = pd.read_pickle(self.df_cache)
        else:
            print("[Classifier] Building taxonomy from CSV...")
            self.df = self._load_and_flatten_tree()
        
        if not force_rebuild and self.index_cache.exists() and self.df_cache.exists():
            print("[Classifier] Loading cached index...")
            try:
                self.index = faiss.read_index(str(self.index_cache))
                self.model = SentenceTransformer(self.model_name)
                print(f"[Classifier] ✓ Loaded {self.index.ntotal} categories")
                return
            except Exception as e:
                print(f"[Classifier] Cache load failed: {e}. Rebuilding...")
        
        # build everything from scratch
        print(f"[Classifier] Loading embedding model {self.model_name}...")
        self.model = SentenceTransformer(self.model_name)
        
        print("[Classifier] Encoding categories...")
        embeddings = self.model.encode(self.df['rich_text'].tolist(), convert_to_numpy=True)
        embeddings = embeddings.astype('float32')
        
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings)
        
        # save for next time
        print("[Classifier] Saving to cache...")
        faiss.write_index(self.index, str(self.index_cache))
        self.df.to_pickle(self.df_cache)
        
        print(f"[Classifier] ✓ Ready with {self.index.ntotal} categories")
    
    def _load_and_flatten_tree(self):
        df = pd.read_csv(self.csv_path)
        
        # Identify leaf nodes (Type level)
        # A node is a leaf if its ID does not appear in the parent_id column
        parent_ids = set(df['parent_id'].dropna().astype(int))
        df['is_leaf'] = ~df['id'].isin(parent_ids)
        
        # Filter to keep ONLY leaf nodes
        df = df[df['is_leaf']].copy()
        print(f"[Classifier] Filtered to {len(df)} leaf nodes (Type level)")
        
        id_to_name = df.set_index('id')['name'].to_dict()
        
        def resolve_path(path_str):
            if pd.isna(path_str):
                return ""
            ids = str(path_str).split('.')
            names = []
            # We need a global lookup for names, not just leaf nodes
            # So let's reload the full DF just for name lookup if needed, 
            # but actually the path string usually contains IDs.
            # Wait, id_to_name only has leaves now. We need full lookup.
            return "" # We'll fix this logic below
            
        # We need full dataframe for name lookup to resolve paths
        full_df = pd.read_csv(self.csv_path)
        full_id_to_name = full_df.set_index('id')['name'].to_dict()
        
        def resolve_path_full(path_str):
            if pd.isna(path_str):
                return ""
            ids = str(path_str).split('.')
            names = []
            for i in ids:
                try:
                    names.append(full_id_to_name.get(int(i), f"Unknown({i})"))
                except ValueError:
                    names.append(f"Invalid({i})")
            return " > ".join(names)
        
        df['rich_text'] = df['path'].apply(resolve_path_full)
        df = df[df['rich_text'] != ""]
        return df
    
    def classify(self, product_data, use_llm=True, top_k=None):
        if self.index is None:
            self.load()
        
        if top_k is None:
            top_k = self.top_k
        
        product_name = product_data.get('product_name', '')
        short_desc = product_data.get('short_description', '')
        long_desc = product_data.get('long_description', '')
        tech_specs = product_data.get('technical_specs', '')
        category = product_data.get('category', '')
        subcategory = product_data.get('subcategory', '')
        
        query_text = f"{product_name} {category} {subcategory} {short_desc}"
        candidates = self._vector_search(product_name, query_text, top_k)
        
        # use LLM if available
        if use_llm and self.llm_client:
            enhanced_desc = f"""Product Name: {product_name}
Category/Subcategory: {category} / {subcategory}
Short Description: {short_desc}
Long Description: {long_desc[:500]}{'...' if len(long_desc) > 500 else ''}
Technical Specs: {tech_specs[:500]}{'...' if len(tech_specs) > 500 else ''}"""
            return self._llm_rerank(product_name, enhanced_desc, candidates)
        else:
            return candidates[0] if candidates else None
    
    def _vector_search(self, product_name, query_text, top_k):
        query_embedding = self.model.encode([query_text], convert_to_numpy=True).astype('float32')
        distances, indices = self.index.search(query_embedding, k=top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            row = self.df.iloc[idx]
            # construct numeric path from row
            numeric_path = str(row['path']) if 'path' in row else str(row['id'])
            results.append({
                "rank": i + 1,
                "id": int(row['id']),
                "name": row['name'],
                "path": row['rich_text'],  # human-readable path
                "numeric_path": numeric_path,  # numeric path like 115547.116749.119494
                "distance": float(distances[0][i])
            })
        return results
    
    def _llm_rerank(self, product_name, product_description, candidates):
        candidates_json = json.dumps(candidates, indent=2)
        
        # simplified prompt
        prompt = f"""You are a product classifier. Pick the best Type-level category ID for this product.
The assignment requires classification at the specific 'Type' level (leaf node).

PRODUCT:
{product_description}

CANDIDATES (All are valid Type-level leaf nodes):
{candidates_json}

Respond with JSON only:
{{
  "selected_type_id": 12345,
  "classification_path": "115547.116749.12345",
  "reasoning": "why this specific type"
}}
"""
        
        try:
            # call appropriate LLM
            if self.llm_provider == 'groq':
                response = self.llm_client.chat.completions.create(
                    model=self.llm_model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=500
                )
                response_text = response.choices[0].message.content.strip()
            else:  # gemini
                response = self.llm_client.generate_content(prompt)  # type: ignore
                response_text = response.text.strip()
            
            # clean up markdown if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            result = json.loads(response_text)
            selected_id = result.get('selected_type_id')
            
            for candidate in candidates:
                if candidate['id'] == selected_id:
                    candidate['llm_reasoning'] = result.get('reasoning', '')
                    # ensure we use the numeric_path from candidate, not LLM's text path
                    if 'numeric_path' in candidate:
                        candidate['classification_path'] = candidate['numeric_path']
                    elif 'classification_path' not in result or not result['classification_path']:
                        # fallback: use numeric_path if LLM didn't provide it
                        candidate['classification_path'] = candidate.get('numeric_path', str(selected_id))
                    else:
                        # use LLM's path if it's numeric
                        llm_path = result.get('classification_path', '')
                        # check if it's numeric path (contains only digits and dots)
                        if llm_path and all(c.isdigit() or c == '.' for c in llm_path):
                            candidate['classification_path'] = llm_path
                        else:
                            candidate['classification_path'] = candidate.get('numeric_path', str(selected_id))
                    return candidate
            
            print(f"[Classifier] Warning: LLM returned ID {selected_id} not in candidates")
            return candidates[0]
        
        except json.JSONDecodeError as e:
            print(f"[Classifier] JSON parsing error: {e}")
            return candidates[0]
        except Exception as e:
            error_msg = str(e)
            
            # handle quota errors
            if "429" in error_msg or "quota" in error_msg.lower() or "rate" in error_msg.lower():
                print("\n" + "="*60)
                print(f"[Classifier] ⚠️  {self.llm_provider.upper()} QUOTA EXCEEDED")
                print("="*60)
                print(f"Your {self.llm_provider.title()} API quota is exhausted.")
                print("\nOptions:")
                print("  1. Wait for quota reset")
                if self.llm_provider == 'gemini':
                    print("  2. Switch to Groq (set LLM_PROVIDER=groq in .env)")
                else:
                    print("  2. Switch to Gemini (set LLM_PROVIDER=gemini in .env)")
                print("  3. Disable LLM in pipelines.py")
                print("\nFalling back to vector search.")
                print("="*60 + "\n")
            else:
                print(f"[Classifier] Error: {error_msg}")
            
            return candidates[0]


# Global singleton instance
_classifier = None

def get_classifier():
    global _classifier
    if _classifier is None:
        _classifier = ProductClassifier()
    return _classifier
