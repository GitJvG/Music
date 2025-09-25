from MA_Scraper.app.db import Session
from MA_Scraper.models import Band, Genre, Discography, \
                        Theme, Users, Similar_band, Candidates, Member, Prefix, Label
from MA_Scraper.Env import Env
from MA_Scraper.Scripts.SQL import refresh_tables
import pandas as pd
import faiss
from collections import defaultdict
import numpy as np
from sqlalchemy import func, select, case, cast, Date, text
import hdbscan

env = Env.get_instance()
faiss.omp_set_num_threads(8)

def split_one_hot_encode(df, multi_value_cols):
    df_result = df.copy()

    for col in multi_value_cols:
        df_result[col] = df_result[col].replace('Not available', '').astype(str)
        df_result[f'{col}_list'] = df_result[col].str.split(',').apply(
            lambda x: [item.strip() for item in x if item.strip()]
        )
        df_exploded_part = df_result[['band_id', f'{col}_list']].explode(f'{col}_list')
    
        exploded_ohe = pd.get_dummies(df_exploded_part[f'{col}_list'], prefix=col, dtype=int)
        df_temp = pd.concat([df_exploded_part[['band_id']], exploded_ohe], axis=1)
        df_aggregated_ohe = df_temp.groupby('band_id').max().reset_index()
        df_result = pd.merge(df_result, df_aggregated_ohe, on='band_id', how='left').fillna(0)
        df_result = df_result.drop(columns=[col, f'{col}_list'])
    
    return df_result

def create_item():
    reviews = select(
        Discography.band_id,
        func.sum(Discography.review_count).label('review_count'),
        func.percentile_cont(0.5).within_group(Discography.review_score).label('median_score')
        ).filter(Discography.reviews.isnot(None)
        ).group_by(Discography.band_id).cte()
    
    genres = select(
        Genre.id
        ).join(Genre.bands).group_by(Genre.id).having(func.count(Band.band_id) >= 15).order_by(func.count(Band.band_id)).cte()
    
    labels = select(
        Label.label_id
        ).join(Label.band).group_by(Label.label_id).having(func.count(Band.band_id) >= 50).order_by(func.count(Band.band_id)).cte()
    
    prefixes = select(
        Prefix.id
        ).join(Prefix.bands).group_by(Prefix.id).having(func.count(Band.band_id) >= 15).order_by(func.count(Band.band_id)).cte()
    
    results = Session.execute(select(
        Band.band_id,
        Band.name.label('band_name'),
        case((Band.label_id.in_(select(labels.c.label_id)), Band.label), else_="Other_Label").label('b_label'),
        Band.country,
        Band.status,
        Band.year_formed,
        func.coalesce(reviews.c.review_count, 0).label('review_count'),
        func.coalesce(reviews.c.median_score, 0).label('median_score'),
        func.coalesce(func.sum((Similar_band.score)), 0).label('score'),
        func.string_agg(func.distinct(Genre.name), ', ').label('genre_names'),
        func.coalesce(func.string_agg(func.distinct(Theme.name), ', '), 'Not available').label('theme_names'),
        func.coalesce(func.string_agg(func.distinct(
            case((Prefix.id.in_(select(prefixes.c.id)), Prefix.name), else_='Other_Prefix')), ', '
            ), 'Not available').label('prefix_names')
    ).join(reviews, onclause=reviews.c.band_id == Band.band_id, isouter=True
    ).join(Band.outgoing_similarities, isouter=True
    ).join(Band.genres, isouter=True
    ).join(Band.themes, isouter=True
    ).join(Band.prefixes, isouter=True
    ).where(Genre.id.in_(select(genres.c.id))
    ).group_by(Band.band_id, Band.name, Band.genre, Band.label, Band.country, Band.status,
               reviews.c.review_count, reviews.c.median_score)
    .having(text('review_count > 0'))).all()

    dataframe = pd.DataFrame(results)
    return dataframe

def create_user():
    user_band_preference_data = Session.execute(select(
        Users.user_id.label('user'),
        Users.band_id,
        case(((Users.liked == True) | (Users.remind_me == True), 1),else_=0).label('label'),
        func.least(func.abs(func.current_date() - cast(Users.liked_date, Date)),
            func.abs(func.current_date() - cast(Users.remind_me_date, Date))).label('relevance')
        )).all()

    users_preference = pd.DataFrame(user_band_preference_data)
    return users_preference

def create_item_embeddings(item):
    ## ['theme_names', 'band_id', 'band_name', 'year_formed']
    multi_valued_categorical_cols = ['prefix_names']
    single_value_categorical_cols = ['country', 'status', 'b_label']
    numerical_columns = ['score', 'review_count', 'median_score']
    cols = multi_valued_categorical_cols + single_value_categorical_cols + numerical_columns + ['band_id']
    item = item[cols]

    processed_df = split_one_hot_encode(item, multi_valued_categorical_cols)
    final_categorical_df = pd.get_dummies(processed_df, columns=single_value_categorical_cols, dtype=int)
    numerical_embeddings = ((item[numerical_columns] - np.mean(item[numerical_columns], axis=0)) / np.std(item[numerical_columns], axis=0)).to_numpy()

    categorical_embeddings = final_categorical_df[[col for col in final_categorical_df.columns if col not in numerical_columns and col not in ['band_id']]].to_numpy()
    clustering_columns = [col for col in processed_df.columns if col.startswith(tuple(multi_valued_categorical_cols))]
    clustering_embeddings = processed_df[clustering_columns].to_numpy()

    item_embeddings_dense = np.hstack([
        categorical_embeddings.astype('float32'),
        numerical_embeddings.astype('float32')
    ])

    return item_embeddings_dense, clustering_embeddings

def cluster(array, disliked_embeddings_array, clustering_array, declustering_embeddings_array, weights, min_cluster_size):
    min_sample_size = int(np.log10(len(clustering_array))+0.5)
    min_cluster_size = int(0.0375*len(clustering_array)+0.5)

    if len(array) < min_cluster_size:
        return [np.mean(array, axis=0)]

    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_sample_size, allow_single_cluster=True, prediction_data=True).fit(clustering_array)
    disliked_labels, strengths = hdbscan.approximate_predict(clusterer, declustering_embeddings_array)
    
    vectors = []
    unique_clusters = np.unique(clusterer.labels_)

    for cluster_label in unique_clusters:
        if cluster_label != -1:
            cluster_indices = (clusterer.labels_ == cluster_label)
            cluster_items_embeddings = array[cluster_indices]
            cluster_weights = weights[cluster_indices]

            disliked_indices = (disliked_labels == cluster_label)
            cluster_disliked_embeddings = disliked_embeddings_array[disliked_indices]
            
            if len(cluster_items_embeddings) > 0:
                vector = np.average(cluster_items_embeddings, axis=0, weights=cluster_weights)
                if len(cluster_disliked_embeddings) > 0:
                    vector = vector - np.mean(cluster_disliked_embeddings, axis=0)
                vectors.append(vector)
    return vectors

def generate_user_vectors(liked_bands, disliked_bands, weights, item_embeddings_array, item_df, clustering_embeddings, min_cluster_size=None):
    liked_embeddings_array = item_embeddings_array[item_df['band_id'].isin(liked_bands)]
    disliked_embeddings_array = item_embeddings_array[item_df['band_id'].isin(disliked_bands)]
    clustering_embeddings_array = clustering_embeddings[item_df['band_id'].isin(liked_bands)]
    declustering_embeddings_array = clustering_embeddings[item_df['band_id'].isin(disliked_bands)]
    user_interest_vectors = cluster(liked_embeddings_array, disliked_embeddings_array, clustering_embeddings_array, declustering_embeddings_array, weights, min_cluster_size)

    print(f"user interest vectors {len(user_interest_vectors)}")
    if not user_interest_vectors:
        user_interest_vectors = np.average(liked_embeddings_array, axis=0, weights=weights)

    user_interest_vectors = np.array(user_interest_vectors).astype('float32')
    return user_interest_vectors

def index_faiss(dense):
    dimension = dense.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(dense)

    return index

def get_filtered_band_members(band_ids):
    bands_with_shared_members_cte = (select(Band.band_id)
        .join(Band.members)
        .where(Member.band_id.in_(band_ids), Member.category.in_(['Current lineup', 'Past lineup'])).distinct()
    ).cte()

    result = Session.execute(
        select(Member.band_id, Member.member_id)
        .where(Member.band_id.in_(select(bands_with_shared_members_cte.c.band_id)), Member.category.in_(['Current lineup', 'Past lineup'])).distinct()
    ).all()

    band_members = defaultdict(set)
    for band_id, member_id in result:
        band_members[band_id].add(member_id)
    return band_members

def get_jaccard(liked_bands):
    band_members = get_filtered_band_members(liked_bands)
    liked_bands = set(liked_bands) & set(band_members.keys())

    union_of_liked_members = set()
    for band_id in liked_bands:
        union_of_liked_members.update(band_members[band_id])

    candidate_bands = set(band_members.keys()) - liked_bands
    jaccard_scores = []

    for candidate_band_id in candidate_bands:
        members_of_candidate_band = band_members[candidate_band_id]

        intersection_size = len(members_of_candidate_band.intersection(union_of_liked_members))
        union_size = len(members_of_candidate_band.union(union_of_liked_members))
        
        jaccard = intersection_size / union_size if union_size != 0 else 0.0
        jaccard_scores[candidate_band_id] = jaccard
    
    jaccard_scores = pd.DataFrame(jaccard_scores, columns=['band_id', 'jaccard_score'])
    return jaccard_scores

def generate_candidates(index, item_df, interacted_bands, liked_bands, user_vectors, k):
    disliked_bands = set(interacted_bands) - set(liked_bands)
    
    if user_vectors.size == 0:
        return []
    k_per_cluster = k // len(user_vectors) + 2

    distances_batch, faiss_indices_batch = index.search(user_vectors, k_per_cluster)

    all_candidates = []

    for cluster_idx in range(len(user_vectors)):
        current_faiss_indices = faiss_indices_batch[cluster_idx]
        current_distances = distances_batch[cluster_idx]

        valid_mask = current_faiss_indices != -1
        valid_indices = current_faiss_indices[valid_mask]
        valid_distances = current_distances[valid_mask]

        if len(valid_indices) > 0:
            temp_df = pd.DataFrame({
                'band_id': item_df.iloc[valid_indices]['band_id'].values,
                'faiss_distance': valid_distances,
                'cluster_id': cluster_idx + 1
            })
            all_candidates.append(temp_df)

    df = pd.concat(all_candidates, ignore_index=True)

    min_distances_df = df.loc[df.groupby('band_id')['faiss_distance'].idxmin()]
    jaccard_scores_df = get_jaccard(liked_bands)
    combined_candidates_df = pd.merge(min_distances_df, jaccard_scores_df, on='band_id', how='outer')
    combined_candidates_df = combined_candidates_df[~combined_candidates_df['band_id'].isin(list(disliked_bands))]

    max_faiss_dist = combined_candidates_df['faiss_distance'].max()
    combined_candidates_df['jaccard_score'] = combined_candidates_df['jaccard_score'].astype(float).fillna(0.0)
    combined_candidates_df['faiss_normalized'] = np.minimum(combined_candidates_df['faiss_distance'] / max_faiss_dist, 1.0)
    combined_candidates_df['score'] = (combined_candidates_df['faiss_normalized'] * 0.8) + \
                                      ((1 - combined_candidates_df['jaccard_score']) * 0.2)
    combined_candidates_df = combined_candidates_df.sort_values(by='score', ascending=True).reset_index(drop=True)
    
    num_new_to_take = int(k * 0.8)
    num_known_to_take = k - num_new_to_take

    combined_candidates_df['is_known'] = combined_candidates_df['band_id'].isin(list(interacted_bands))
    new_candidates_df = combined_candidates_df[~combined_candidates_df['is_known']].head(num_new_to_take)[['band_id', 'cluster_id', 'score']]
    known_candidates_df = combined_candidates_df[combined_candidates_df['is_known']].head(num_known_to_take)[['band_id', 'cluster_id', 'score']]

    new_candidates = list(new_candidates_df.itertuples(index=False, name=None))
    known_candidates = list(known_candidates_df.itertuples(index=False, name=None))

    return new_candidates + known_candidates

def main(min_cluster_size=None, k=800):
    item = create_item()
    item_embeddings, clustering_embeddings = create_item_embeddings(item)
    users_preference = create_user()

    candidate_list = []
    for user_id in users_preference[users_preference['label'] == 1]['user'].unique():
        user_preference = users_preference[(users_preference['user'] == user_id) & (users_preference['band_id'].isin(item['band_id']))]

        interacted_bands = user_preference['band_id'].unique().astype('int64').tolist()
        liked_bands = user_preference[user_preference['label'] == 1]['band_id'].unique().astype('int64').tolist()
        disliked_bands = user_preference[user_preference['label'] == 0]['band_id'].unique().astype('int64').tolist()
        band_relevance_map = user_preference[user_preference['label'] == 1].set_index('band_id')['relevance'].to_dict()
        
        relevances = np.array([band_relevance_map[band_id] for band_id in liked_bands])
        weights = 1.0 / (relevances + 1e-6)

        user_vectors = generate_user_vectors(liked_bands, disliked_bands, weights, item_embeddings, item, clustering_embeddings, min_cluster_size)
        index = index_faiss(item_embeddings)

        candidates = generate_candidates(index, item, interacted_bands, liked_bands, user_vectors, k)
        for candidate, cluster_id, score in candidates:
            candidate_list.append({'user_id': user_id, 'band_id': candidate, 'cluster_id': cluster_id, 'score': score})

    candidate_df = pd.DataFrame(candidate_list)
    candidate_df.to_csv(env.candidates.path, index=False)

def complete_refresh(min_cluster_size=None, k=800):
    main(min_cluster_size, k)
    refresh_tables([Candidates])

if __name__ == '__main__':
    complete_refresh()