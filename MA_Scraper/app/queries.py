from sqlalchemy import func, select, case
from MA_Scraper.app.db import Session
from MA_Scraper.models import Band, Discography, Similar_band, Genre, Prefix
from datetime import datetime

def Top_albums(band_ids, picks_per_band=1):
    ranked_albums_subquery = select(
        Band.band_id,
        Discography.name,
        Discography.type,
        Band.name.label('band_name'),
        func.coalesce(Discography.review_score * Discography.review_count, 0).label('weighted_score'),
    ).join(Discography.band).where(Discography.band_id.in_(band_ids), Discography.type.in_(["Full-length", "Split", "EP", "Demo"])).cte("ranked_albums_subquery")

    band_averages = select(
        ranked_albums_subquery.c.band_id,
        func.avg(ranked_albums_subquery.c.weighted_score).label('weighted_score')
    ).group_by(ranked_albums_subquery.c.band_id).cte()

    ranked_albums_with_row_num = (select(
        ranked_albums_subquery,
        func.row_number().over(
            partition_by=ranked_albums_subquery.c.band_id,
            order_by=(
                case((ranked_albums_subquery.c.weighted_score >= band_averages.c.weighted_score, 0), else_=1),
                case((ranked_albums_subquery.c.weighted_score >= band_averages.c.weighted_score, func.random()), 
                     else_=ranked_albums_subquery.c.weighted_score).desc()
                     )).label('rank')
    ).join(band_averages, onclause= band_averages.c.band_id == ranked_albums_subquery.c.band_id)).cte("ranked_albums_with_row_num")

    selected_albums = Session.execute(select(
            ranked_albums_with_row_num.c.band_id,
            ranked_albums_with_row_num.c.name,
            ranked_albums_with_row_num.c.type,
            ranked_albums_with_row_num.c.band_name,
            func.string_agg(Prefix.name, ', ').label('genre')
        )
        .join(Band, onclause=ranked_albums_with_row_num.c.band_id == Band.band_id)
        .join(Band.prefixes)
        .where(ranked_albums_with_row_num.c.rank <= picks_per_band)
        .group_by(ranked_albums_with_row_num.c.band_id,
            ranked_albums_with_row_num.c.name,
            ranked_albums_with_row_num.c.type,
            ranked_albums_with_row_num.c.band_name)
        ).all()

    return selected_albums

def New_albums(query_limit=10, min_year=None):
    limit1 = int(query_limit / 2)
    limit2 = query_limit - limit1
    if not min_year:
        if datetime.today().month > 1:
            min_year = datetime.today().year
        else:
            min_year = datetime.today().year-1

    agg_band_cte = (select(Band.band_id,
            func.sum(Discography.review_count * Discography.review_score).label('total_reviews')
        ).join(Band.genres).join(Band.discography_items)
        .group_by(Band.band_id)).cte('agg_band_cte')
    
    recent_albums_ranked_by_year = (
        select(
            Discography.band_id,
            Discography.album_id,
            Discography.name,
            Discography.type,
            Discography.year.label('album_year'),
            Discography.review_score,
            Discography.review_count,
            Band.name.label('band_name'),
            func.row_number().over(partition_by=Discography.band_id,order_by=Discography.year.desc()).label("rank_by_year")
        ).join(Discography.band).where(Discography.year >= min_year,
            Discography.type.in_(['Full-length', 'EP', 'Split', 'Demo']))).cte('recent_albums_ranked_by_year')
    
    latest_albums_ranked = (select(
            recent_albums_ranked_by_year,
            func.row_number().over(partition_by=recent_albums_ranked_by_year.c.band_id,order_by=(recent_albums_ranked_by_year.c.review_score * recent_albums_ranked_by_year.c.review_count).desc()).label("rank_by_score")
        ).where(recent_albums_ranked_by_year.c.review_score > 0)).cte('latest_albums_ranked')

    first_branch_results = Session.execute(
        select(
            latest_albums_ranked.c.band_id,
            latest_albums_ranked.c.name,
            latest_albums_ranked.c.type,
            latest_albums_ranked.c.band_name,
            func.string_agg(Prefix.name, ', ').label('genre')
        )
        .join(agg_band_cte, agg_band_cte.c.band_id == latest_albums_ranked.c.band_id)
        .join(Band, onclause=latest_albums_ranked.c.band_id == Band.band_id)
        .join(Band.prefixes)
        .where(latest_albums_ranked.c.rank_by_score == 1)
        .group_by(latest_albums_ranked.c.band_id,
            latest_albums_ranked.c.name,
            latest_albums_ranked.c.type,
            latest_albums_ranked.c.band_name)
        .order_by(None).order_by(func.random()).limit(limit1)
    ).all()
    
    selected_band_ids = [row.band_id for row in first_branch_results]

    band_scores = (select(Similar_band.band_id,
        func.sum(Similar_band.score).label("total_score")
        ).group_by(Similar_band.band_id)).cte('band_scores')

    second_results = Session.execute(
        select(
             recent_albums_ranked_by_year.c.band_id,
             recent_albums_ranked_by_year.c.name,
             recent_albums_ranked_by_year.c.type,
             recent_albums_ranked_by_year.c.band_name,
             func.string_agg(Prefix.name, ', ').label('genre')
        )
        .join(band_scores, recent_albums_ranked_by_year.c.band_id == band_scores.c.band_id, isouter=True)
        .join(agg_band_cte, agg_band_cte.c.band_id == recent_albums_ranked_by_year.c.band_id)
        .join(Band, onclause=recent_albums_ranked_by_year.c.band_id == Band.band_id)
        .join(Band.prefixes)
        .where(recent_albums_ranked_by_year.c.rank_by_year == 1, band_scores.c.total_score > 50, recent_albums_ranked_by_year.c.band_id.notin_(selected_band_ids)
                ,agg_band_cte.c.total_reviews > 0)
        .group_by(recent_albums_ranked_by_year.c.band_id,
            recent_albums_ranked_by_year.c.name,
            recent_albums_ranked_by_year.c.type,
            recent_albums_ranked_by_year.c.band_name)
        .order_by(None).order_by(func.random()).limit(limit2)
    ).all()

    final_combined_results = first_branch_results + second_results
    return final_combined_results
