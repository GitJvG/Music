from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, DeclarativeBase
from flask_login import UserMixin
from sqlalchemy import Column, Integer, String, BigInteger, Text, LargeBinary, DateTime, Boolean, Numeric, SmallInteger, ForeignKey, ForeignKeyConstraint

class Base(DeclarativeBase):
    pass

class BandGenres(Base):
    __tablename__ = 'band_genres'
    band_id = Column(BigInteger, ForeignKey('band.band_id'), primary_key=True)
    id = Column(SmallInteger, ForeignKey('genre.id'), primary_key=True)

    band_obj = relationship('Band', viewonly=True)
    genre_item = relationship('Genre', viewonly=True)

class BandPrefixes(Base):
    __tablename__ = 'band_prefixes'
    band_id = Column(BigInteger, ForeignKey('band.band_id'), primary_key=True)
    id = Column(SmallInteger, ForeignKey('prefix.id'), primary_key=True)

    band_obj = relationship('Band', viewonly=True)
    prefix_item = relationship('Prefix', viewonly=True)

class Themes(Base):
    __tablename__ = 'themes'
    band_id = Column(BigInteger, ForeignKey('band.band_id'), primary_key=True)
    theme_id = Column(SmallInteger, ForeignKey('theme.theme_id'), primary_key=True)

    band = relationship('Band', viewonly=True)
    theme = relationship("Theme", viewonly=True)

class Genre(Base):
    __tablename__ = 'genre'
    id = Column(SmallInteger, primary_key=True)
    name = Column(Text, unique=True, nullable=False)

    bands = relationship('Band', secondary=BandGenres.__table__, back_populates='genres')

class Prefix(Base):
    __tablename__ = 'prefix'
    id = Column(SmallInteger, primary_key=True)
    name = Column(Text, unique=True, nullable=False)

    bands = relationship('Band', secondary=BandPrefixes.__table__, back_populates='prefixes')

class Theme(Base):
    __tablename__ = 'theme'
    theme_id = Column(SmallInteger, primary_key=True)
    name = Column(Text, unique=True, nullable=False)

    bands = relationship('Band', secondary=Themes.__table__, back_populates='themes')

class Band(Base):
    __tablename__ = 'band'
    band_id = Column(BigInteger, primary_key=True)
    name = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    genre = Column(Text, nullable=True)
    location = Column(Text, nullable=True)
    status = Column(Text, nullable=True)
    year_formed = Column(SmallInteger, nullable=True)
    theme = Column('themes', Text, nullable=True)
    label = Column(Text, nullable=True)
    label_id = Column(Integer, ForeignKey('label.label_id'), nullable=True)
    years_active = Column(Text, nullable=True)

    discography_items = relationship("Discography", back_populates="band")
    members = relationship("Member", back_populates="band")
    logo = relationship("Band_logo", uselist=False, back_populates="band")
    band_label = relationship("Label", back_populates="band")

    user_interactions = relationship("Users", back_populates="band_obj")
    candidate_users_link = relationship("Candidates", back_populates="band_obj")
    outgoing_similarities  = relationship("Similar_band", foreign_keys="Similar_band.band_id", back_populates="source_band")
    incoming_similarities  = relationship("Similar_band", foreign_keys="Similar_band.similar_id", back_populates="similar_band")

    genres = relationship(Genre, secondary=BandGenres.__table__, back_populates='bands')
    prefixes = relationship(Prefix, secondary=BandPrefixes.__table__, back_populates='bands')
    themes = relationship(Theme, secondary=Themes.__table__, back_populates="bands")

class Discography(Base):
    __tablename__ = 'discography'
    band_id = Column(BigInteger, ForeignKey('band.band_id'), primary_key=True, nullable=False)
    album_id = Column(Integer, primary_key=True, nullable=False)
    name = Column( Text, nullable=False)
    type = Column(Text, nullable=True)
    year = Column(SmallInteger, nullable=True)
    reviews = Column(Text, nullable=True)
    review_count = Column(SmallInteger, nullable=True)
    review_score = Column(SmallInteger, nullable=True)

    band = relationship(Band, back_populates="discography_items")

class Similar_band(Base):
    __tablename__ = 'similar_band'
    band_id = Column(BigInteger, ForeignKey('band.band_id'), primary_key=True)
    similar_id = Column(BigInteger, ForeignKey('band.band_id'), primary_key=True)
    score = Column(SmallInteger, nullable=True)

    source_band = relationship(Band, foreign_keys=[band_id], back_populates="outgoing_similarities")
    similar_band = relationship(Band, foreign_keys=[similar_id], back_populates="incoming_similarities")

class Label(Base):
    __tablename__ = 'label'
    label_id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    country = Column(Text, nullable=True)
    genre = Column(Text, nullable=True)
    status = Column(Text, nullable=True)

    band = relationship(Band, back_populates="band_label")

class Member(Base):
    __tablename__ = 'member'
    band_id = Column(BigInteger, ForeignKey('band.band_id'), primary_key=True)
    member_id = Column(BigInteger, primary_key=True, nullable=False)
    name = Column(Text, nullable=True)
    role = Column(Text, nullable=True)
    category = Column(Text, nullable=False)

    band = relationship(Band, back_populates="members")

class Band_logo(Base):
    __tablename__ = 'band_logo'
    band_id = Column(BigInteger, ForeignKey('band.band_id', deferrable=True, initially='DEFERRED'), primary_key=True)
    data = Column(LargeBinary, nullable=False)
    retrieved_at = Column(DateTime(timezone=True), default=func.now())
    content_type = Column(Text, nullable=False)

    band = relationship(Band, back_populates="logo")

class User(Base, UserMixin):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password = Column(String(128), nullable=False)
    birthyear = Column(SmallInteger, nullable=False)
    gender = Column(String(10), nullable=False)
    nationality = Column(String(50), nullable=False)
    genre1 = Column(String(50), nullable=False)
    genre2 = Column(String(50), nullable=False)
    genre3 = Column(String(50), nullable=False)

    user_interactions = relationship("Users", back_populates="user")
    candidate_bands_link = relationship("Candidates", back_populates="user")

class Users(Base):
    __tablename__ = 'users'
    user_id = Column(Integer, ForeignKey('user.id'), primary_key=True)
    band_id = Column(BigInteger, ForeignKey('band.band_id'), primary_key=True)
    liked = Column(Boolean, nullable=True)
    liked_date = Column(DateTime, nullable=True)
    remind_me = Column(Boolean, nullable=True)
    remind_me_date = Column(DateTime, nullable=True)

    user = relationship(User, back_populates="user_interactions")
    band_obj = relationship(Band, back_populates="user_interactions")

class User_albums(Base):
    __tablename__ = 'user_albums'
    user_id = Column(Integer, ForeignKey('user.id'), primary_key=True)
    band_id = Column(BigInteger, primary_key=True)
    album_id = Column(Integer, primary_key=True)
    status = Column(Text, nullable=True)
    modified_date = Column(DateTime, nullable=True)
    creation_date = Column(DateTime, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ['band_id', 'album_id'],
            ['discography.band_id', 'discography.album_id']),{})

class Candidates(Base):
    __tablename__ = 'candidates'
    user_id = Column(Integer, ForeignKey('user.id'), primary_key=True, nullable=False)
    band_id = Column(BigInteger, ForeignKey('band.band_id'), primary_key=True, nullable=False)
    cluster_id = Column(SmallInteger, nullable=False)
    score = Column(Numeric, nullable=True)
    
    user = relationship(User, back_populates="candidate_bands_link")
    band_obj = relationship(Band, back_populates="candidate_users_link")