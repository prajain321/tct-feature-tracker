# schema of mongodb database
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.json_util import dumps
from bson.json_util import loads


class Database:
    def __init__(self,collection):
        self.client = MongoClient("mongodb://10.130.163.167:27017")
        self.db = self.client["tickets"]
        self.collection = self.db[collection]

    def get_all_collections(self):
        return self.client.get_database("tickets").list_collection_names()
    def iscollection_present(self):
        return self.collection.name in self.client.get_database("tickets").list_collection_names()
    def insert(self, data):
        return self.collection.insert_many(data).acknowledged
    
    def find(self, id):
        return self.collection.find_one({"_id": id})
    
    def find_all(self):
        return self.collection.find()
    
    def delete(self, id):
        return self.collection.delete_one({"_id": id}).acknowledged
    
    def delete_all(self):
        return self.collection.delete_many({}).acknowledged
    
    def update(self, id, data):
        # i want to update everything except comments
        return self.collection.update_one({"_id": id}, {"$set": data})
    
    def delete_collection(self):
        return self.db.drop_collection(self.collection.name)
    
    def update_effort(self, id, data):
        return self.collection.update_one({"_id": id}, {"$set": {"Effort": data}}).acknowledged
    
    def count(self):
        return self.collection.count_documents({})
    
    def update_comments(self, id, data):
        return self.collection.update_one({"_id": id}, {"$push": {"comments": data}}).acknowledged
    
    def close(self):
        self.client.close()

# arr = ['7.2', '7.1']
# for i in arr:
#     db=Database(i)
#     print(db.delete_collection()) #db.delete_collection()
# db=Database('7.2')
# print(db.iscollection_present())
# print(db.update_effort(id="SWDEV-562745" , data='XL'))