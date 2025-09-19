import unicodedata
from nltk.stem import WordNetLemmatizer, PorterStemmer

from MA_Scraper.Env import Env
env = Env.get_instance()
lemmatizer = WordNetLemmatizer()
stemmer = PorterStemmer()

def basic_processing(df_series):
    processed_series = df_series.astype(str)
    
    processed_series = (
        processed_series.str.lower()
        .str.replace(r'\(.*?\)', '', regex=True)
        .str.replace(r'\s?/\s', '/', regex=True)
    )
    
    processed_series = (
        processed_series.str.replace(r'[^\x20-\x7E]', '', regex=True) 
        .str.replace(r'\b(of|the|a|an|to)\b', '', regex=True)
        .str.replace(r';', ',', regex=True)
        .str.replace(r'/', ',', regex=True)
        .str.replace(r'\band\b', ',', regex=True)
        .str.replace(r'[()]+', '', regex=True)
        .str.replace(r'\s*,\s*', ',', regex=True)
        .str.replace(r'\s+', ' ', regex=True)
        .str.strip()
    )

    def process_individual_themes(theme_string):
        if not isinstance(theme_string, str) or not theme_string:
            return None
        
        normalized = unicodedata.normalize('NFD', theme_string)
        ascii_text = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
        
        themes = []
        for theme in ascii_text.split(','):
            theme = theme.strip()
            if not theme:
                continue

            longest_word = max(theme.split(), key=len, default='')
            if not longest_word:
                continue
            
            lemmatized_word = lemmatizer.lemmatize(longest_word)
            stemmed_word = stemmer.stem(lemmatized_word)
            themes.append(stemmed_word)
        
        return ','.join(themes) if themes else None

    processed_series = processed_series.apply(process_individual_themes)
    return processed_series.str.strip().replace('', None)