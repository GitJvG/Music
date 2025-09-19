"""Script to push all data to SQL, currently fully cascades the existing DB out of convenience"""
import pandas as pd
from MA_Scraper.app.db import Session, engine
from MA_Scraper.models import Base
from MA_Scraper.models import Member, Similar_band, Discography, Band, Genre, Prefix, BandGenres, BandPrefixes, Theme, Themes, Candidates, Label
from sqlalchemy import text
from MA_Scraper.Env import Env

env = Env.get_instance()

dataframes = {
    Member.__name__: lambda: pd.read_csv(env.memb.path, dtype=env.memb.mapping, engine='pyarrow', header=0, keep_default_na=False, na_values=['', 'N/A']),
    Similar_band.__name__: lambda: pd.read_csv(env.simi.path, dtype=env.simi.mapping, engine='pyarrow', header=0),
    Discography.__name__: lambda: pd.read_csv(env.disc.path, dtype=env.disc.mapping, engine='pyarrow', header=0, keep_default_na=False, na_values=['', 'N/A']),
    Band.__name__: lambda: pd.read_csv(env.fband.path, dtype=env.fband.mapping, engine='pyarrow', header=0, keep_default_na=False, na_values=['', 'N/A']),
    Genre.__name__: lambda: pd.read_csv(env.genre.path, dtype=env.genre.mapping, header=0),
    Prefix.__name__: lambda: pd.read_csv(env.prefix.path, dtype=env.prefix.mapping, header=0),
    BandGenres.__name__: lambda: pd.read_csv(env.band_genres.path, dtype=env.band_genres.mapping, engine='pyarrow', header=0),
    BandPrefixes.__name__: lambda: pd.read_csv(env.band_prefixes.path, dtype=env.band_prefixes.mapping, engine='pyarrow', header=0),
    Theme.__name__: lambda: pd.read_csv(env.theme.path, dtype=env.theme.mapping, header=0, keep_default_na=False, na_values=['', 'N/A']),
    Themes.__name__: lambda: pd.read_csv(env.themes.path, dtype=env.themes.mapping, engine='pyarrow', header=0),
    Candidates.__name__: lambda: pd.read_csv(env.candidates.path, dtype=env.candidates.mapping, header=0, keep_default_na=False, na_values=['', 'N/A']),
    Label.__name__: lambda: pd.read_csv(env.label.path, dtype=env.label.mapping, engine='pyarrow', header=0, keep_default_na=False, na_values=['', 'N/A'])
}

def refresh_tables(model=None):
    """Fully drops and truncates model before recreating it, this is done to overcome annoying relationship spaggetthi"""
    models = model if model else [Label, Band, Theme, Prefix, Genre, Discography, Similar_band, Member, BandGenres, BandPrefixes, Themes]

    for model in models:
        df = dataframes.get(model.__name__)()
        if df is None or df.empty:
            raise ValueError(f"DataFrame for model '{model.__name__}' is empty or None.")
        
    for model in models:
        Session.execute(text(f'DROP TABLE IF EXISTS "{model.__tablename__}" CASCADE;'))
    Session.commit()

    Base.metadata.create_all(engine, checkfirst=False)
    Label.__table__.drop()
    for model in models:
        df = dataframes.get(model.__name__)()
        df.to_sql(model.__tablename__, con=engine, if_exists='append', index=False)

    print("All tables refreshed successfully with constraints applied.")

if __name__ == "__main__":
    refresh_tables()