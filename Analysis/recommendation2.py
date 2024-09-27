import pandas as pd
import sys
import os
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from CleanGenre import process_genres
from Cleancountry import standardize_country_name, add_geographic_similarity_to_band

# Load environment variables and database connection
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv()

# Constants for dataset paths
LYRICS = os.getenv('BANLYR')
BANDSFILE = os.getenv('BANDPAR')
SIMILAR = os.getenv('SIMBAN')
similar_artists_df = pd.read_csv(SIMILAR)
lyrics_df = pd.read_csv(LYRICS)
bands_df = pd.read_csv(BANDSFILE, usecols=['Band Name', 'Country', 'Genre', 'Band ID'])

def normalize(x):
    return (x - x.min()) / (x.max() - x.min())

def preproc_data():
    """Transforms, merges and processes datasets."""
    global bands_df
    global lyrics_df
    bands_df = process_genres(bands_df, 'Genre')
    
    # Preprocess themes
    lyrics_df['Themes:'] = lyrics_df['Themes:'].str.split(',')
    lyrics_df['Themes:'] = lyrics_df['Themes:'].apply(lambda x: ', '.join(theme.strip() for theme in x if isinstance(x, list) and theme.strip()) if isinstance(x, list) else x)
    lyrics_df = lyrics_df.dropna(subset=['Themes:'])
    lyrics_df = lyrics_df[lyrics_df['Themes:'] != '']
    lyrics_df['Themes:'] = lyrics_df['Themes:'].str.lower()

    # Merge datasets
    merged_df = pd.merge(bands_df, lyrics_df, how='inner', on='Band ID')
    # Normalize country names in countries_df
    countries_df = pd.read_csv('Datasets/Countries.csv')
    countries_df['country'] = countries_df['country'].str.strip().str.lower()
    valid_countries_set = set(countries_df['country'].unique())

    #Add a standardized column to later join on.
    merged_df = merged_df.merge(
        countries_df[['country', 'longitude', 'latitude']],
        left_on=merged_df['Country'].apply(standardize_country_name),  # Standardize during merge
        right_on='country',
        how='left'  # Use left join to keep all bands data
    )

    return merged_df

def filter_by_genre_overlap(merged_df, band_id):
    """Filters bands based on genre overlap."""
    band_info = merged_df[merged_df['Band ID'] == band_id]
    
    if band_info.empty:
        return pd.DataFrame()

    band_genres = band_info['Processed Genre'].values[0]

    # Directly filter without creating a column
    overlap_bands_df = merged_df[merged_df['Processed Genre'].apply(lambda genres: any(band_genre in genres for band_genre in band_genres))].reset_index(drop=True)
    
    return overlap_bands_df
    
def calculate_similarity(overlap_bands_df, band_id, column):
    """Calculates similarity based on a given column and modifies dataframe in place."""
    if overlap_bands_df.empty:
        print("No similar bands found with overlapping genres.")
        return None

    # Compute TF-IDF matrix for the overlapping bands
    tfidf_vectorizer = TfidfVectorizer()
    tfidf_matrix = tfidf_vectorizer.fit_transform(overlap_bands_df[column])

    # Dimensionality reduction
    n_components = min(20, tfidf_matrix.shape[1])
    svd = TruncatedSVD(n_components=n_components)
    tfidf_matrix_reduced = svd.fit_transform(tfidf_matrix)

    # Compute cosine similarity matrix
    cosine_sim_matrix = cosine_similarity(tfidf_matrix_reduced)

    # Find the index of the current band
    band_idx = overlap_bands_df[overlap_bands_df['Band ID'] == band_id].index[0]

    # Get similarity scores
    similarity_scores = cosine_sim_matrix[band_idx]

    # Add similarity scores as a new column (in-place)
    overlap_bands_df[f'{column}_Similarity'] = similarity_scores

    # Drop the original column only if it exists. It's not needed after calculation
    if column in overlap_bands_df.columns:
        overlap_bands_df.drop(columns=[column], inplace=True)
    return similarity_scores

def get_complete_similar_bands(band_id):
    filtered_similar_bands = similar_artists_df[
        (similar_artists_df['Band ID'] == band_id) | (similar_artists_df['Similar Artist ID'] == band_id)
    ]
    bands_listing_original = similar_artists_df[similar_artists_df['Similar Artist ID'] == band_id]
    complete_bands = pd.concat([
        filtered_similar_bands[['Similar Artist ID', 'Score']],
        bands_listing_original[['Band ID', 'Score']].rename(columns={'Band ID': 'Similar Artist ID'})
    ])
    return aggregate_similar_bands(complete_bands)

def aggregate_similar_bands(filtered_df):
    aggregated_df = filtered_df.groupby('Similar Artist ID', as_index=False).agg({'Score': 'max'})
    return aggregated_df.sort_values(by='Score', ascending=False).reset_index(drop=True)

def normalize_score(series):
    """Normalize the score series to a range of 0 to 1."""
    return (series - series.min()) / (series.max() - series.min())

def get_recommendations(band_id, genre_weight, lyrical_weight, similar_weight, country_weight): 
    """Fetches recommendations for a specific band based on weighted scores."""
    # Step 1: Read and merge datasets
    merged_df = preproc_data()

    # Step 2: Get complete similar bands
    similar_bands_df = get_complete_similar_bands(band_id)
    
    # Step 3: Filter on processed genre overlap
    overlap_bands_df = filter_by_genre_overlap(merged_df, band_id)
    overlap_bands_df.drop(columns=['Processed Genre'], inplace=True)

    # Calculate similarity based on genre and lyrics
    calculate_similarity(overlap_bands_df, band_id, 'Genre')
    calculate_similarity(overlap_bands_df, band_id, 'Themes:')

    # Get the similarity scores from the similar bands DataFrame, with a fallback to 0 for missing scores
    overlap_bands_df['Similar_Band_Score'] = similar_bands_df.set_index('Similar Artist ID').reindex(overlap_bands_df['Band ID'], fill_value=0)['Score'].values

    overlap_bands_df = add_geographic_similarity_to_band(overlap_bands_df, band_id)

    # Normalize the similarity scores
    overlap_bands_df['Themes:_Similarity'] = normalize_score(overlap_bands_df['Themes:_Similarity'])
    overlap_bands_df['Genre_Similarity'] = normalize_score(overlap_bands_df['Genre_Similarity'])
    overlap_bands_df['Similar_Band_Score'] = normalize_score(overlap_bands_df['Similar_Band_Score'])
    overlap_bands_df['Country_Similarity'] = normalize_score(overlap_bands_df['Country_Similarity'])
    # Calculate the total score
    overlap_bands_df['Total_Score'] = (
        lyrical_weight * overlap_bands_df['Themes:_Similarity'] +
        similar_weight * overlap_bands_df['Similar_Band_Score'] +
        genre_weight * overlap_bands_df['Genre_Similarity'] +
        country_weight * overlap_bands_df['Country_Similarity']
    )
    # Drop the indiv score columns
    overlap_bands_df.drop(columns=['Themes:_Similarity', 'Similar_Band_Score', 'Genre_Similarity', 'Country_Similarity'], inplace=True)
    
    # Sort and select top recommendations
    recommended_bands = overlap_bands_df[overlap_bands_df["Band ID"] != band_id].nlargest(10, 'Total_Score')

    return recommended_bands

# Example of fetching recommendations for a band
recommendations = get_recommendations(115, genre_weight=0.333, lyrical_weight=0.333, similar_weight=0.333, country_weight=0.1)  # Adjust weights as needed
print("\nRecommendations based on Similar Bands and Genres:")
print(recommendations)