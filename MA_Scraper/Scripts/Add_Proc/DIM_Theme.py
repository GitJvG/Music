import pandas as pd
from MA_Scraper.Env import Env
env = Env.get_instance()
from MA_Scraper.Scripts.Add_Proc.Helper.CleanThemes import basic_processing
import pickle

def save_DIM_themes(anchor_groups):
    anchors = list(anchor_groups.keys())

    theme = pd.DataFrame({
        'theme_id': range(1, len(anchors) + 1),
        'name': anchors
    })
    theme.to_csv(env.theme.path, index=False)

def save_Bandthemes(anchor_groups):
    bridge_data = []
    theme_df = pd.read_csv(env.theme.path, dtype=env.theme.mapping, engine='pyarrow')
    # For each band, get the themes and their corresponding anchors
    df = pd.read_csv(env.deta.path, dtype=env.deta.mapping, engine='pyarrow')
    df['themes'] = basic_processing(df['themes'].dropna())
    df = df.dropna(subset='themes')

    anchor_name_to_id = theme_df.set_index('name')['theme_id'].to_dict()

    theme_to_anchor_map = {}
    for anchor, themes_list in anchor_groups.items():
        theme_to_anchor_map[anchor.lower()] = anchor
        for theme in themes_list:
            theme_to_anchor_map[theme.lower()] = anchor

    for band_id, themes_str in zip(df['band_id'], df['themes']):
        processed_themes = themes_str.split(',')
        band_anchors = set() 
        for theme in processed_themes:
            theme = theme.strip()
            anchor_name = theme_to_anchor_map.get(theme)
            if anchor_name:
                anchor_id = anchor_name_to_id.get(anchor_name)
                if anchor_id is not None:
                    band_anchors.add((band_id, anchor_id))
                    
        bridge_data.extend(list(band_anchors))

    themes_df = pd.DataFrame(bridge_data, columns=['band_id', 'theme_id'])
    themes_df.to_csv(env.themes.path, index=False)

def main():
    with open(env.dim_theme_dict, 'rb') as pickle_file:
        anchor_groups = pickle.load(pickle_file)
    save_DIM_themes(anchor_groups)
    save_Bandthemes(anchor_groups)

if __name__ == '__main__':
    main()