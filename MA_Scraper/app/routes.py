from flask import Blueprint, request, url_for, jsonify, g, Response
from flask_login import login_required, current_user
from sqlalchemy import func, and_, or_, select
from MA_Scraper.app.db import Session
from MA_Scraper.models import Band, Users, Discography, Similar_band, Genre, Prefix, Candidates, Band_logo, User_albums
from MA_Scraper.app import cache_manager
from MA_Scraper.app.utils import render_with_base, Like_bands
from MA_Scraper.app.queries import Top_albums, New_albums
import random
import asyncio
import aiohttp
from datetime import datetime
from MA_Scraper.app.YT import YT
from math import ceil
from functools import wraps

main = Blueprint('main', __name__)

from MA_Scraper.app.auth import auth as auth_blueprint
from MA_Scraper.app.extension import extension as extension_blueprint
main.register_blueprint(auth_blueprint)
main.register_blueprint(extension_blueprint)

today = datetime.today().date()
random.seed(today.year * 100 + today.month * 10 + today.day)

ROWS = {
    ('/ajax/remind'): 1,
    ('/ajax/featured'): 1,
    ('/ajax/recommended_albums'): 3,
    ('/ajax/known_albums'): 3,
    ('/band/<int:band_id>'): 1,
}

def apply_query_limit(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        endpoint = request.path
        count = min(int(request.args.get('count', 1)), 8)
        limit = ROWS.get((endpoint), 1) * count
        kwargs['query_limit'] = limit

        return await func(*args, **kwargs)
    return wrapper

def jsonify_with_row(data):
    endpoint = request.path
    rows = ROWS.get((endpoint), 1)
    return jsonify({
        'data': data,
        'rowsCount': rows,
    })

def get_band_data(band_id):
    band_data = Session.execute(select(Band.band_id, 
            Band.name.label('band_name'),
            func.string_agg(Genre.name, ', ').label('genre_string'))
                    .join(Band.genres)
                    .where(Band.band_id == band_id)
                    .group_by(Band.band_id, Band.name)).all()
    if band_data:
        return {
                "band_id": band_data[0].band_id,
                "name": band_data[0].band_name,
                "genre": band_data[0].genre_string,
            }

    return None

async def fetch_video_for_album(band_id, album_name, album_type, band_name, band_genre, result):
    if album_name:
        video_query = f"{band_name} {album_name} {'Full Album' if album_type == 'Full-length' else album_type}"

        video_response = await YT.get_video(video_query)
        
        if 'video_url' in video_response.json:
            result.append({
                "band_id": band_id,
                "name": band_name,
                "album_name": album_name,
                "album_type": album_type,
                "genre": band_genre,
                "video_url": video_response.json['video_url'],
                "playlist_url": video_response.json['playlist_url'] if video_response.json['playlist_url'] else False,
                "thumbnail_url": video_response.json['thumbnail_url'] if video_response.json['thumbnail_url'] else None
            })

async def fetch_top_albums_with_videos(albums):
    result = []
    tasks = []

    for band_id, album_name, album_type, band_name, band_genre in albums:
        task = fetch_video_for_album(band_id, album_name, album_type, band_name, band_genre, result)
        tasks.append(task)

    await asyncio.gather(*tasks)
    return result

@main.route('/', methods=['GET'])
def index():
    return render_with_base('index.html', main_content_class="index")

@main.route('/ajax/featured')
@apply_query_limit
async def featured(query_limit):
    cache = cache_manager.get_cache()
    if cache:
        return jsonify_with_row(cache)

    alb = New_albums(query_limit)
    result = await fetch_top_albums_with_videos(alb)
    cache_manager.set_cache(result)

    return jsonify_with_row(result)

@main.route('/ajax/remind')
@login_required
@apply_query_limit
async def fetch_remind(query_limit):
    cache = cache_manager.get_cache()
    if cache:
        return jsonify_with_row(cache)
    
    bands = Session.scalars(
    select(Users.band_id).where(Users.user_id == current_user.id, Users.remind_me == True)
    .order_by(func.random()).limit(query_limit)
    ).all()
    
    Albums = Top_albums(bands)

    result = await fetch_top_albums_with_videos(Albums)
    cache_manager.set_cache(result)

    return jsonify_with_row(result)
    
@main.route('/ajax/recommended_albums')
@login_required
@apply_query_limit
async def fetch_albums(query_limit):
    cache = cache_manager.get_cache()
    if cache:
        return jsonify_with_row(cache)
    
    band_ids = Session.scalars(select(Candidates.band_id)
    .outerjoin(Users, and_(Users.band_id == Candidates.band_id, Users.user_id == Candidates.user_id))
    .join(Discography, Discography.band_id == Candidates.band_id)
    .where(Discography.type.in_(["Full-length", "Split", "EP"]), (Users.liked.is_not(False)),
           (Candidates.user_id == current_user.id))
    .group_by(Candidates.band_id)
    #.having(func.sum(Discography.review_score) > 0)
    .order_by(func.random()).limit(query_limit)).all()
    Albums = Top_albums(band_ids)
    
    result = await fetch_top_albums_with_videos(Albums)
    cache_manager.set_cache(result)
    return jsonify_with_row(result)

@main.route('/ajax/top_albums')
@login_required
async def fetch_above_avg_albums():
    bands = [int(band) for band in request.args.getlist('bands')]
    ppb = min(int(request.args.get('count', 1)), 8)

    Albums = Top_albums(bands, ppb)
    result = await fetch_top_albums_with_videos(Albums)
    return jsonify_with_row(result)
    
@main.route('/ajax/known_albums')
@login_required
@apply_query_limit
async def fetch_known_albums(query_limit):
    cache = cache_manager.get_cache()
    if cache:
        return jsonify_with_row(cache)
    
    bands = (select(Users.band_id)
    .where(Users.user_id == current_user.id, Users.liked == True).distinct()).cte()
    bands = Session.scalars(select(bands).order_by(func.random()).limit(query_limit)).all()

    Albums = Top_albums(bands)
    result = await fetch_top_albums_with_videos(Albums)
    cache_manager.set_cache(result)

    return jsonify_with_row(result)
    
@main.route('/like_band', methods=['POST'])
@login_required
def like_band():
    user_id = current_user.id
    data = request.get_json()
    band_id = data.get('band_id')
    action = data.get('action')

    liked_state, remind_state = Like_bands(user_id, band_id, action)
    return jsonify({'status': 'success', 'liked_state': liked_state, 'remind_me_state': remind_state}), 200

@main.route('/my_bands')
@login_required
def my_bands():
    user_id = current_user.id

    user_interactions = Session.execute(select(
            Band.band_id,
            Band.name,
            Users.liked,
            Users.liked_date)
        .join(Band.user_interactions)
        .filter(Users.user_id == user_id).order_by(Users.liked_date.desc()).limit(50)).all()

    band_data = [
        {'band_id': band_id, 'name': name, 'liked': liked, 'liked_date': liked_date}
        for band_id, name, liked, liked_date in user_interactions
    ]
    
    return render_with_base('my_bands.html', band_data=band_data)

@main.route('/feedback/ajax')
@login_required
def get_bands():
    user_id = current_user.id
    user_interactions = (
        Session.execute(select(
            Band.band_id,
            Band.name,
            Users.liked,
            Users.liked_date,
            Users.remind_me,
            Users.remind_me_date
        ).join(Band.user_interactions)
        .where(Users.user_id == user_id)).all())

    band_data = [
        {'band_id': band_id, 'name': name, 'liked': liked, 'liked_date': liked_date, 'remind_me': remind_me, 'remind_me_date': remind_me_date}
        for band_id, name, liked, liked_date, remind_me, remind_me_date in user_interactions
    ]
    return jsonify(band_data)

@main.route('/import')
@login_required
def imports():
    return render_with_base('import.html')

@main.route('/get_genres', methods=['GET'])
def get_genres():
    genres = Session.scalars(select(Genre.name).distinct()).all()
    return jsonify(genres)

@main.route('/search', methods=['POST', 'GET'])
def search():
    if request.method == 'POST':
        query = request.form.get('q', '').strip()
        matches = (
            Session.query(Band.band_id, Band.name)
            .filter(or_(func.unaccent(func.lower(Band.name)).ilike(f"{query.lower()} %"), func.unaccent(func.lower(Band.name)).ilike(f"{query.lower()}")))
            .all()
        )
        if len(matches) == 1:
            return jsonify({
                'success': True,
                'redirect_url': url_for('main.band_detail', band_id=matches[0].band_id)
            })
        return jsonify({
            'success': True,
            'redirect_url': url_for('main.search', query=query),
        })
    query = request.args.get('query', '')
    return render_with_base('search.html', query=query)

@main.route('/search_results')
def query():
    query = request.args.get('query', '').strip().lower()
    page = request.args.get('page', 1, type=int)
    per_page = 100

    exact_matches = (
        Session.query(Band.band_id, Band.name, Band.genre, Band.country)
        .filter(func.unaccent(func.lower(Band.name)) == query.lower())
    )

    partial_matches = (
        Session.query(Band.band_id, Band.name, Band.genre, Band.country)
        .filter(or_(Band.name.ilike(f'% {query} %'), Band.name.ilike(f'{query} %')))
    )

    exact_matches_page = exact_matches.paginate(page=page, per_page=per_page, error_out=False)
    partial_matches_page = partial_matches.paginate(page=page, per_page=per_page, error_out=False)

    matches = exact_matches_page.items + [match for match in partial_matches_page.items if match not in exact_matches_page.items]

    total_matches = exact_matches.count() + partial_matches.count()
    total_pages = ceil(total_matches / per_page)

    return jsonify(
        results=[{
            'name': band.name,
            'band_id': band.band_id,
            'genre': band.genre,
            'country': band.country
        } for band in matches],
        total_pages=total_pages,
        current_page=page
    )

@main.route('/band/<int:band_id>')
@login_required
def band_detail(band_id):
    band = Session.execute(select(Band, Users.liked, Users.remind_me).outerjoin(Band.user_interactions)
                              .where(Band.band_id == band_id, or_(Users.user_id == current_user.id, Users.user_id == None))).first()
    discography = Session.execute(select(Discography).where(Discography.band_id == band_id).order_by(Discography.year.asc(), Discography.album_id.asc())).scalars().all()
    similar_bands = Session.execute(select(Similar_band.similar_id, Band.name, Band.country, Band.genre, Band.status, Band.label).join(Similar_band.similar_band) \
        .where(Similar_band.band_id==band_id).order_by(Similar_band.score.desc())).all()
    types = {album.type for album in discography}

    albums = [
        {
            'album_name': album.name,
            'album_id': album.album_id,
            'type': album.type,
            'year': album.year,
            'reviews': album.reviews,
        }
        for album in discography
    ]

    similar = [
        {
            'id': sim.similar_id,
            'name': sim.name,
            'country': sim.country,
            'genre': sim.genre,
            'label': sim.label,
            'status': sim.status
        }
        for sim in similar_bands
    ]

    return render_with_base('band_detail.html', band=band[0], liked=band[1], remind_me=band[2], albums=albums, types=types, similar=similar, title=band[0].name)

async def fetch_head(session: aiohttp.ClientSession, url: str):
    async with session.head(url, allow_redirects=True) as response:
        return response.status, url

async def fetch_image(session: aiohttp.ClientSession, url: str):
    async with session.get(url) as response:
        if response.status == 200:
            return await response.read(), response.content_type
        return None, None

@main.route('/ajax/band_logo/<int:band_id>')
async def get_band_logo(band_id):
    stored_logo = Session.get(Band_logo, band_id)
    if stored_logo and stored_logo.data and stored_logo.content_type:
        return Response(stored_logo.data, mimetype=stored_logo.content_type)
    
    async with aiohttp.ClientSession() as http_session:
        band_id_str = str(band_id)
        digits = "/".join(band_id_str[:4])
        file_extensions = ['jpg', 'png', 'gif', 'jpeg']
        urls = [f"https://www.metal-archives.com/images/{digits}/{band_id_str}_logo.{ext}" for ext in file_extensions]

        responses = await asyncio.gather(*[fetch_head(http_session, url) for url in urls])

        for attempt in range(2):
            for (status, resolved_url), ext in zip(responses, file_extensions):
                if status == 200 and resolved_url:
                    image_data, content_type = await fetch_image(http_session, resolved_url)
                    if image_data and content_type:
                        new_logo = Band_logo(band_id=band_id, data=image_data, content_type=content_type)
                        Session.add(new_logo)
                        Session.commit()
                        return Response(image_data, mimetype=content_type)
        return jsonify('')
    
@main.route('/update_album_status',methods=['POST'])
def update_album_status():
    data = request.get_json()
    album_id = data.get('album_id')
    band_id = data.get('band_id')
    new_status = data.get('status')
    now = datetime.now().replace(microsecond=0)

    existing_preference = Session.query(User_albums).filter_by(user_id=current_user.id, album_id=album_id, band_id=band_id).first()
    if existing_preference:
        existing_preference.status = new_status
        existing_preference.modified_date = now
    else:
        new_preference = User_albums(user_id=current_user.id, band_id=band_id, album_id=album_id, status=new_status, creation_date=now, modified_date=now)
        Session.add(new_preference)
    Session.commit()

    return jsonify({
        "album_id": album_id,
        "new_status": new_status,
    }), 200

@main.route('/algorithm', methods=['GET'])
def clusters():
    base = (select(Candidates.cluster_id, Candidates.band_id, Candidates.score, Band.name, Genre.name.label('genre_name'), Genre.id.label('genre_id'), Prefix.name.label('prefix_name'), Prefix.id.label('prefix_id')).join(Candidates.band_obj).join(Band.genres).join(Band.prefixes, isouter=True).where(Candidates.user_id == current_user.id)).cte()
    dc = select(base.c.cluster_id, base.c.band_id, base.c.name, base.c.score, base.c.prefix_name).distinct().cte()
    candidates = select(dc.c.cluster_id, dc.c.band_id, dc.c.name, dc.c.score, func.string_agg(dc.c.prefix_name, ', ').label('prefix_name')
                        ,func.row_number().over(partition_by=dc.c.cluster_id, order_by=dc.c.score.desc()).label('rn')).distinct().group_by(dc.c.cluster_id, dc.c.band_id, dc.c.name, dc.c.score).cte()
    candidates = Session.execute(select(candidates.c.cluster_id, candidates.c.band_id, candidates.c.name, candidates.c.prefix_name, candidates.c.score).where(candidates.c.rn < 6)).all()

    gbase = (select(base.c.cluster_id, base.c.band_id, base.c.genre_name, base.c.genre_id, base.c.score).distinct()).cte()
    cluster_header = (select(gbase.c.cluster_id, gbase.c.genre_name, func.row_number().over(partition_by=gbase.c.cluster_id, order_by=func.sum(gbase.c.score).desc()).label("rank")).group_by(gbase.c.cluster_id, gbase.c.genre_name)).cte()
    top_cluster_genre_header = Session.execute(select(cluster_header.c.cluster_id, func.string_agg(cluster_header.c.genre_name, ', ').label('genre_names')).where(cluster_header.c.rank <= 3).group_by(cluster_header.c.cluster_id)).all()

    prefix_header = (select(base.c.cluster_id, base.c.prefix_name, func.row_number().over(partition_by=base.c.cluster_id, order_by=func.count(base.c.prefix_id).desc()).label("rank")).group_by(base.c.cluster_id, base.c.prefix_name)).cte()
    top_cluster_prefix_header = Session.execute(select(prefix_header.c.cluster_id, func.string_agg(prefix_header.c.prefix_name, ', ').label('prefix_names')).where(prefix_header.c.rank <= 3).group_by(prefix_header.c.cluster_id)).all()
    
    candidate_list = [{"cluster": candidate.cluster_id, "band_id": candidate.band_id, "band_name": candidate.name, "genre_name": candidate.prefix_name, "score": candidate.score} for candidate in candidates]

    top_cluster_header = {
    entry.cluster_id: {"cluster": entry.cluster_id, "genre_names": entry.genre_names, "prefix_names": None}
    for entry in top_cluster_genre_header
    }
    
    for entry in top_cluster_prefix_header:
        cluster_id = entry.cluster_id
        if cluster_id in top_cluster_header:
            top_cluster_header[cluster_id]["prefix_names"] = entry.prefix_names

    top_cluster_header = list(top_cluster_header.values())
    
    return render_with_base('algorithm.html', candidates=candidate_list, clusters=top_cluster_header)