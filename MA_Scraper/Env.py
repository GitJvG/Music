import json
import os
import httpx
from MA_Scraper.models import BigInteger, Integer, Text, Numeric, SmallInteger, DateTime, LargeBinary, Band, Similar_band, \
    Discography, Member, Label, Band_logo, Genre, Prefix, BandPrefixes, BandGenres, Theme, Themes, Candidates
project_root = os.path.abspath(os.path.dirname(__file__))

config_yaml = os.path.join(project_root, 'config.yaml')
config_json = os.path.join(project_root, 'config.json')

type_mapping = {
    BigInteger: 'int64[pyarrow]',
    Integer: 'int32[pyarrow]',
    Text: 'string',
    Numeric: 'float64[pyarrow]',
    SmallInteger: 'int16[pyarrow]',
    DateTime: 'string',
    LargeBinary: 'object'
}

def pandas_dtype(model, type_mapping=type_mapping):
    """Returns the pandas dtype dictionary for the SQLalchemy model"""
    dtypes_dict = {}
    for column in model.__table__.columns:
        sqlalchemy_type = type(column.type)
        
        pandas_dtype = type_mapping.get(sqlalchemy_type)
        if pandas_dtype:
            dtypes_dict[column.name] = pandas_dtype
        else:
            print(f"Warning: No pandas dtype mapping found for SQLAlchemy type {sqlalchemy_type}. Column '{column.name}' will be inferred.")
    return dtypes_dict

def dpath(file):
    return os.path.join(project_root, 'Datasets', file)

def load_config(attribute, config_file=config_json):
    try:
        with open(config_file, 'r') as file:
            config = json.load(file)
        value = config.get(attribute)
        if value is None:
            raise ValueError(f"Missing required configuration: {attribute}")
        return value
    except Exception as e:
        print(f"Error loading {config_file}: {e}")
        raise

class FileInfo:
    def __init__(self, file_path, dtypes_mapping, key):
        self.path = file_path
        self.mapping = dtypes_mapping
        self.key = key

class Env:
    _instance = None
    
    @staticmethod
    def get_instance():
        if Env._instance is None:
            Env._instance = Env()
        return Env._instance

    def __init__(self):
        if Env._instance is not None:
            raise Exception("This is a singleton!")
        
        try:
            self.head =         load_config('headers')
            self.cook =         load_config('cookies')
            self.fire =         load_config('Firefox_cookies.sqlite')

        except ValueError as e:
            print(f"Error: {e}")
            raise

        self.meta = FileInfo(dpath('metadata.csv'), {
                                                    'name': 'string',
                                                    'date': 'string',
                                                    'time': 'string'
                                                    }, ['name'])
        self.simi = FileInfo(dpath('MA_Similar.csv'), pandas_dtype(Similar_band), ['band_id', 'similar_id'])
        self.disc = FileInfo(dpath('MA_Discog.csv'), pandas_dtype(Discography), ['album_id', 'band_id'])
        self.band = FileInfo(dpath('MA_Bands.csv'), pandas_dtype(Band), ['band_id'])
        self.deta = FileInfo(dpath('MA_Details.csv'), pandas_dtype(Band), ['band_id'])
        self.memb = FileInfo(dpath('MA_Member.csv'), pandas_dtype(Member), ['band_id', 'member_id'])
        self.label = FileInfo(dpath('MA_Label.csv'), pandas_dtype(Label), ['label_id'])
        self.reviews = FileInfo(dpath('MA_Reviews.csv'), {
                                                        'album_id': 'int64[pyarrow]',
                                                        'review_id': 'int64[pyarrow]',
                                                        'title': 'string',
                                                        'username': 'string',
                                                        'review_text': 'string'
                                                        }, ['album_id', 'review_id'])
        self.fband = FileInfo(dpath('band.csv'), pandas_dtype(Band), ['band_id'])
        self.genre = FileInfo(dpath('genre.csv'), pandas_dtype(Genre), [None])
        self.prefix = FileInfo(dpath('prefix.csv'), pandas_dtype(Prefix), [None])
        self.band_logo = FileInfo(dpath('band_logo.csv'), pandas_dtype(Band_logo), [None])
        self.band_genres = FileInfo(dpath('band_genres.csv'), pandas_dtype(BandGenres), [None])
        self.band_prefixes = FileInfo(dpath('band_prefixes.csv'), pandas_dtype(BandPrefixes), [None])
        self.theme = FileInfo(dpath('theme.csv'), pandas_dtype(Theme), [None])
        self.dim_theme_dict = dpath('Temp/DIM_Theme_Dict.pkl')
        self.themes = FileInfo(dpath('themes.csv'), pandas_dtype(Themes), [None])
        self.candidates = FileInfo(dpath('candidates.csv'), pandas_dtype(Candidates), [None])

        self.url_modi =     "https://www.metal-archives.com/archives/ajax-band-list/by/modified/selection/"
        self.url_band =     "https://www.metal-archives.com/browse/ajax-letter/json/1/l/"
        self.url_label =    "https://www.metal-archives.com/label/ajax-list/json/1/l/"
        self.url_reviews =  "https://www.metal-archives.com/reviews/1/1/"
        self.url_similar =  "https://www.metal-archives.com/band/ajax-recommendations/id/"
        self.url_disc1 =    "https://www.metal-archives.com/band/discography/id/"
        self.url_disc2 =    "/tab/all"
        self.url_deta =     "https://www.metal-archives.com/bands/id/"

        self.retries =      10
        self.delay =        0.45
        self.batch_size =   1000

        self.client = httpx.Client(http2=True, headers=self.head, cookies=self.cook)

        self.ytbackend =    "SCRAPE"
        # Backend for importing playlist data and embedding videos. Options: "YTDLP" and "SCRAPE". 
        # YTDLP: No setup required and unlimited usage
        # SCRAPE: Best search results as it includes playlists and embeds them as a video list that automatically plays all videos. 
