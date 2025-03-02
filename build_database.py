# scripts/build_database.py
import sqlite3
import os
import sys
import platform
import nltk
from nltk.corpus import wordnet
import argparse

def get_database_path():
    """Get appropriate database path for current platform"""
    system = platform.system()
    
    # Base directory for app data
    if system == 'Windows':
        base_dir = os.path.join(os.environ.get('APPDATA', ''), 'QuickDefinition')
    elif system == 'Darwin':  # macOS
        base_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'QuickDefinition')
    else:  # Linux and others
        base_dir = os.path.join(os.path.expanduser('~'), '.quickdefinition')
    
    # Create directory if it doesn't exist
    os.makedirs(base_dir, exist_ok=True)
    
    return os.path.join(base_dir, 'wordnet.db')

def setup_database(custom_path=None):
    """Create and populate WordNet database"""
    db_path = custom_path if custom_path else get_database_path()
    
    print(f"Setting up WordNet database at: {db_path}")
    
    # Download WordNet data if needed
    try:
        print("Checking NLTK WordNet data...")
        nltk.data.find('corpora/wordnet')
    except LookupError:
        print("WordNet data not found. Downloading now...")
        nltk.download('wordnet')
    
    # Create database
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Create table
    c.execute('''
    CREATE TABLE IF NOT EXISTS definitions (
        id INTEGER PRIMARY KEY,
        lemma TEXT,
        part_of_speech TEXT,
        synset TEXT,
        definition TEXT,
        example TEXT
    )
    ''')
    
    # Create indices for faster lookup
    c.execute('CREATE INDEX IF NOT EXISTS idx_lemma ON definitions(lemma)')
    
    # Check if the database already has data
    c.execute('SELECT COUNT(*) FROM definitions')
    count = c.fetchone()[0]
    
    if count > 0:
        print(f"Database already contains {count} entries. Skip population? (y/n)")
        response = input().lower()
        if response == 'y':
            conn.close()
            return
    
    # Populate the database with WordNet entries
    print("Populating database from WordNet...")
    
    # Get all synsets
    all_synsets = list(wordnet.all_synsets())
    total = len(all_synsets)
    
    for i, synset in enumerate(all_synsets):
        # Show progress every 1000 synsets
        if i % 1000 == 0:
            print(f"Processing synset {i+1}/{total}...")
        
        pos = synset.pos()
        definition = synset.definition()
        examples = synset.examples()
        
        # Get all lemmas for this synset
        for lemma in synset.lemma_names():
            # Skip very long words or phrases with spaces
            if len(lemma) > 50 or ' ' in lemma:
                continue
                
            # Replace underscores with spaces
            lemma = lemma.replace('_', ' ')
            
            # Insert into database
            for example in examples or [None]:
                c.execute('''
                INSERT INTO definitions (lemma, part_of_speech, synset, definition, example)
                VALUES (?, ?, ?, ?, ?)
                ''', (lemma, pos, str(synset), definition, example))
    
    # Commit changes and close connection
    conn.commit()
    conn.close()
    
    print("Database setup complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Set up WordNet database for Quick Definition app')
    parser.add_argument('--path', help='Custom path for the database file')
    args = parser.parse_args()
    
    setup_database(args.path)