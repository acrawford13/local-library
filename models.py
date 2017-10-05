from sqlalchemy import Column, Integer, String, ForeignKey, Float, Unicode, DateTime, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
from math import sqrt
import re

Base = declarative_base()

class User(Base):
    __tablename__ = 'user'
    username = Column(String, primary_key=True)
    name = Column(String)
    email = Column(String, unique=True)
    city = Column(String)
    country = Column(String)
    location_lat = Column(Float)
    location_lng = Column(Float)
    picture = Column(String)

    @hybrid_method
    def distance(self, target, precision=2):
        if precision > 0:
            return round(sqrt(((self.location_lat - float(target['lat']))**2) + ((self.location_lng - float(target['lng']))**2))*111.0, precision)
        else:
            return int(round(sqrt(((self.location_lat - float(target['lat']))**2) + ((self.location_lng - float(target['lng']))**2))*111.0, precision))

    @distance.expression
    def distance(self, target):
        return ((self.location_lat - target['lat'])*(self.location_lat - target['lat'])) + ((self.location_lng - target['lng'])*(self.location_lng - target['lng']))

class Book(Base):
    __tablename__ = 'book'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    author = Column(String)
    owner_username = Column(String, ForeignKey('user.username'))
    owner = relationship(User)
    date_added = Column(DateTime)
    description = Column(String)
    UniqueConstraint(owner_username,slug,name='_username_slug_uc')

    @property
    def serialize_book_owner(self):
        return {
            "name":self.name,
            "author":self.author,
            "date_added":self.date_added,
            "slug":self.slug,
            "description":self.description,
            "owner":{
                "name":self.owner.name,
                "username":self.owner_username,
                "country":self.owner.country,
                "city":self.owner.city,
                "picture":self.owner.picture,
            }
        }

    @property
    def serialize_book(self):
        return {
            "name":self.name,
            "author":self.author,
            "date_added":self.date_added,
            "slug":self.slug,
            "description":self.description,
        }

    def serialize_with_distance(self, location):
        return {
            "name":self.name,
            "author":self.author,
            "date_added":self.date_added,
            "slug":self.slug,
            "owner":{
                "name":self.owner.name,
                "username":self.owner_username,
                "country":self.owner.country,
                "city":self.owner.city,
                "picture":self.owner.picture,
            },
            "description":self.description,
            "distance":self.owner.distance(location),
        }

engine = create_engine('sqlite:///catalog.db')
Base.metadata.create_all(engine)
