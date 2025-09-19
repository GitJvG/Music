import os
import pandas as pd
from rapidfuzz import fuzz
from collections import Counter
import pickle
from collections import defaultdict
from MA_Scraper.Scripts.Add_Proc.Helper.CleanThemes import basic_processing
from MA_Scraper.Env import Env
env = Env.get_instance()

OTHER = 'other_topic'

def items_to_set(genre_series):
    theme_set = set()
    theme_count = Counter()
    for genre_string in genre_series:
        if pd.notna(genre_string):
            genre_string = genre_string.strip()
            if genre_string:
                for genre in genre_string.split(','):
                    genre_cleaned = genre.strip()
                    if len(genre_cleaned) <= 40 and genre_cleaned:
                        theme_set.add(genre_cleaned)
                        theme_count[genre_cleaned] += 1
    return theme_set, theme_count

def group_themes(themes, theme_count, threshold=85):
    sorted_themes = sorted(themes, key=lambda theme: (theme_count[theme]), reverse=True)
    
    theme_dict = defaultdict(list)
    grouped_themes_tracker = set()

    for theme in sorted_themes:
        if theme in grouped_themes_tracker:
            continue

        found_group = False
        for anchor_word in list(theme_dict.keys()): 
            if fuzz.token_set_ratio(anchor_word, theme, score_cutoff=threshold):
                theme_dict[anchor_word].append(theme)
                grouped_themes_tracker.add(theme)
                found_group = True
                break

        if not found_group:
            if theme_count[theme] < 45:
                theme_dict[OTHER].append(theme)
                grouped_themes_tracker.add(theme)
            else:
                anchor_word = max(theme.split(), key=len) if theme.split() else theme
                theme_dict[anchor_word].append(theme)
                grouped_themes_tracker.add(theme)
    
    return theme_dict

def consolidate_anchors(initial_clusters, merge_threshold):
    anchors = {a for a in initial_clusters.keys() if a != OTHER}
    sorted_anchors = sorted(
        list(anchors), 
        key=lambda x: (len(x), x)
    )
    
    merged_anchors_tracker = set()
    consolidated_anchors = set() 

    for current_anchor in sorted_anchors:
        if current_anchor in merged_anchors_tracker:
            continue

        consolidated_anchors.add(current_anchor)
        
        for other_anchor in sorted_anchors:
            if other_anchor == current_anchor or other_anchor in merged_anchors_tracker:
                continue

            score1 = fuzz.token_set_ratio(current_anchor, other_anchor)
            score2 = fuzz.partial_token_set_ratio(current_anchor, other_anchor)
            combined_score = (score1 + score2) / 2

            if combined_score >= merge_threshold:
                merged_anchors_tracker.add(other_anchor)
                
    return consolidated_anchors

def find_best_anchor_match(item, anchors, threshold=90):
    best_match_anchor = None
    highest_score = -1.0

    for anchor_word in anchors:
        score_to_anchor = fuzz.ratio(anchor_word, item)
        score_to_anchor2 = fuzz.partial_token_set_ratio(anchor_word, item)
        combined_score = (score_to_anchor + score_to_anchor2) / 2

        if combined_score > highest_score and combined_score >= threshold:
            highest_score = combined_score
            best_match_anchor = anchor_word
            
    return best_match_anchor

def reassign_themes(anchors, all_unique_themes, threshold):
    final_clusters = defaultdict(list)
    for theme in all_unique_themes:
        best_match_anchor = find_best_anchor_match(theme, anchors, threshold)
        if best_match_anchor:
            final_clusters[best_match_anchor].append(theme)
        else:
            final_clusters[OTHER].append(theme)
    
    return final_clusters

def load_existing_dict(pickle_path):
    if os.path.exists(pickle_path):
        with open(pickle_path, 'rb') as pickle_file:
            return pickle.load(pickle_file)
    else:
        return defaultdict(list)

def find_new_themes(theme_set, existing_dict):
    existing_themes = set(existing_dict.keys()).union(
        {theme for themes in existing_dict.values() for theme in themes}
    )
    new_themes = theme_set - existing_themes
    return new_themes

def update_theme_dict(new_themes, existing_dict, threshold=85):
    anchors = set(existing_dict.keys()) - {OTHER}

    for theme in new_themes:
        best_match_anchor = find_best_anchor_match(theme, anchors, threshold)
        if best_match_anchor:
            existing_dict[best_match_anchor].append(theme)
        else:
            existing_dict[OTHER].append(theme)
    return existing_dict

def main():
    df = pd.read_csv(env.deta.path, dtype=env.deta.mapping, engine='pyarrow')['themes']
    df = basic_processing(df.dropna())

    themes, theme_count = items_to_set(df)
    clusters = group_themes(themes, theme_count, 93)
    anchors = consolidate_anchors(clusters, 93)
    clusters = reassign_themes(anchors, themes, 90)
    
    with open(env.dim_theme_dict, 'wb') as pickle_file:
        pickle.dump(clusters, pickle_file)

def update_pickle():
    df = pd.read_csv(env.deta.path, dtype=env.deta.mapping, engine='pyarrow')['themes']
    df = basic_processing(df.dropna())

    output_path = env.dim_theme_dict
    
    theme_set, theme_count = items_to_set(df)
    existing_dict = load_existing_dict(output_path)
    
    new_themes = find_new_themes(theme_set, existing_dict)
    updated_dict = update_theme_dict(new_themes, existing_dict)
    
    with open(output_path, 'wb') as pickle_file:
        pickle.dump(updated_dict, pickle_file)

if __name__ == "__main__":
    main()
