import pandas as pd
from MA_Scraper.Env import Env
env = Env.get_instance()

def main():
    band = pd.read_csv(env.band.path, dtype=env.band.mapping, keep_default_na=False, na_values=['', 'N/A'])
    details = pd.read_csv(env.deta.path, dtype=env.deta.mapping, keep_default_na=False, na_values=['', 'N/A'])
    full_band = band.merge(details, on='band_id', how='left')
    full_band['year_formed'] = pd.to_numeric(full_band['year_formed'], errors='coerce')
    full_band['year_formed'] = full_band['year_formed'].astype('Int64')
    full_band['label_id'] = pd.to_numeric(full_band['label_id'], errors='coerce')
    full_band['label_id'] = full_band['label_id'].astype('Int64')
    full_band.to_csv(env.fband.path, index=False)