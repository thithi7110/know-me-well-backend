import os
import random
from string import Template
from typing import Type
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from aws_lambda_powertools import Logger
from pydantic import BaseModel
from boto3.dynamodb.conditions import Key, Attr
import boto3
import uuid
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import base64
# 環境変数取得
ENV = os.environ['ENV']
STORAGE_FAVORITEDB_NAME = os.environ.get("STORAGE_FAVORITEDB_NAME")

# boto3 初期化
ddb = boto3.resource("dynamodb", region_name="us-east-1")
table = ddb.Table(STORAGE_FAVORITEDB_NAME)

# s3クライアント　初期か
s3 = boto3.client('s3', region_name="us-east-1")

## FastAPI 初期化
app = FastAPI(
    title="KMWAPI",
    root_path=f"/{ENV}",
    openapi_url="/openapi.json"
)

# ロガー初期化
app.logger = Logger(level="INFO", service=__name__)

# CORS設定
allow_origins = ['http://localhost:3000']
if 'ALLOW_ORIGIN' in os.environ.keys():
    allow_origins.append(os.environ['ALLOW_ORIGIN'])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# スキーマ設定
class Imageinfo(BaseModel):
    """
    リクエスト用 Favorite内部使用
    """
    datapaths:list[str]
    position:list[str]
    size:list[str]
    tag:str
    datas:list[str]

#S3へのアップロード用
class ImageDataForS3(BaseModel):
    """
    S3登録用 
    """
    imageName:str
    data:str
    
class Favorite(BaseModel):
    """
    リクエスト登録用 Favorite
    """
    id:str
    userid:str
    imageinfo:Imageinfo

class ImageinfoUpdate(BaseModel):
    """
    DB登録用 Favorite内部使用
    """
    datapaths:list[str]
    position:list[str]
    size:list[str]
    tag:str
    
class FavoriteUpdate(BaseModel):
    """
    DB登録用 Favorite
    """
    id:str
    userid:str
    imageinfo:ImageinfoUpdate
    
class RequestFavorite(BaseModel):
    """
    レスポンススキーマ
    """
    favorites:list[Favorite]
    
class ResponseFavorite(BaseModel):
    """
    レスポンススキーマ
    """
    favorites:list[Favorite]
    
# class ResponseFavoriteImages(BaseModel):
#     """
#     レスポンススキーマ
#     """
#     id: str
#     userid:str
#     tag:str
#     datas: list[str]
#     position:list[str]
    
@app.get("/favorites")
def get_Favorites_list():
    """
    Favorite 一覧を取得する
    """
    # Favorite 一覧取得処理を書く
    return {
        "id": "1",
        "name": "Favorite-1",
        "description": "hogehogehoge"
    }

# @app.get("/favorites/{id}")
@app.get("/favorites/{userid}")
def get_Favorite_item(userid: str):
    """
    Favorite アイテムを取得する
    """
    print("get_Favorite_item")
    # key = {
    #     "id": {'S':id},
    #     "userid":{'S',"100001"}
    # }

    # response = table.get_item(Key=key)
    
    #get userinfo data from dynamonDB
    favorites = table.query(
    IndexName='userid',
    KeyConditionExpression=Key('userid').eq(userid))
    
    response:ResponseFavorite = []
    
    for favorite in favorites['Items']:
        datas:list[str] = []
        for datapath in favorite["imageinfo"]["datapaths"]:            
            #get s3 data by userid
            BUCKET = 'know-me-well-bucket'
            KEY = userid+'/'+datapath
            obj = s3.get_object(Bucket=BUCKET, Key=KEY)
            file_stream = obj['Body'].read()
            # #拡張子取得
            # splitetext = str(os.path.splitext(datapath)[1])
            # splitetext = splitetext.replace('.','')
            # content = ""
            # byteBase64 = base64.b64encode(file_stream)
            # # byteBase64 = base64.b64encode(obj['Body'])
            # content = byteBase64.decode("utf-8")
            # datas.append(f"data:image/{splitetext};base64,{content}")
            datas.append(file_stream)

        response.append(Favorite(
            id=favorite["id"],
            userid=favorite["userid"],
            imageinfo=Imageinfo(
                datapaths=favorite["imageinfo"]["datapaths"],
                position=favorite["imageinfo"]["position"],
                size=favorite["imageinfo"]["position"],
                tag=favorite["imageinfo"]["tag"],
                datas=datas
            )
        ))
            
    # templates = Jinja2Templates(directory="templates")
    # return templates.TemplateResponse(
    #     "template.html",
    #     {
    #         "request":request,
    #         "datas": contents
    #     }
    # )
    # return ResponseFavoriteImages.parse_obj({"datas":contents})
    
    
    # returen ResponseFavorite.parse_obj((response["Items"])[0])
    return response

@app.post("/favorites")
def post_Favorite_item(Favorite_in: RequestFavorite):
    """
    Favorite アイテムを取得する
    """
    print("start----->")
    #userid取得
    userid = Favorite_in.favorites[0].userid
    
    #更新対象となるデータを取得する
    favoritesOrg = table.query(
    IndexName='userid',
    KeyConditionExpression=Key('userid').eq(userid))
    
    #紐づくS3を削除
    print("紐づくS3を削除----->")
    for favorite in favoritesOrg['Items']:
        for datapath in favorite["imageinfo"]["datapaths"]:            
            BUCKET = 'know-me-well-bucket'
            KEY = userid+'/'+datapath
            s3.delete_object(Bucket=BUCKET, Key=KEY)
    
    #Dynamoからデータを削除しておく
    print("Dynamoからデータを削除しておく----->"+userid)
    # table.delete_item(
    # IndexName='userid',
    # KeyConditionExpression=Key('userid').eq(userid))
    favorites = table.query(
        IndexName='userid',
        KeyConditionExpression=Key('userid').eq(userid)
    )
    for favorite in favorites['Items']:
        table.delete_item(
            Key={
                'id':favorite["id"],
                'userid':userid
            }
        )
    
    
    #リクエストの情報でDynamoDBを登録しながらS3のデータも登録していく
    print("リクエストの情報でDynamoDBを登録しながらS3のデータも登録していく----->")
    favoriteupds:list[FavoriteUpdate] = []
    for favorite in Favorite_in.favorites:
        #datasをs3用にパスを付けなおし、別オブジェクトにする
        wkimagedatafors3:list[ImageDataForS3] = []
        # wkimageinf = ImageinfoUpdate(
        #     datapaths=[],
        #     position=favorite.imageinfo.position,
        #     size=favorite.imageinfo.size,
        #     tag=favorite.imageinfo.tag
        # )
        datapaths:list[str]=[]
        for i in range(len(favorite.imageinfo.datas)):
            imagepath = str(uuid.uuid4())
            #s3用
            wkimagedatafors3.append(ImageDataForS3(
                imageName=imagepath,
                data=favorite.imageinfo.datas[i]
            ))
            
            #s3登録
            BUCKET = 'know-me-well-bucket'
            KEY = userid+'/'+imagepath
            # upds3 = ImageDataForS3(
            #     imageName=imagepath,
            #     data=favorite.imageinfo.datas[i]
            # )
            s3.put_object(Bucket=BUCKET, Key=KEY,Body=favorite.imageinfo.datas[i])
            
            #Dynamo用
            datapaths.append(imagepath)
        
        #dynamo更新用のオブジェクト
        id = str(uuid.uuid4())
        imageinfo = ImageinfoUpdate(
                datapaths=datapaths,
                position=favorite.imageinfo.position,
                size=favorite.imageinfo.size,
                tag=favorite.imageinfo.tag
            )
        print(imageinfo)
        favoriteupds.append(FavoriteUpdate(
            id=id,
            userid=userid,
            imageinfo=imageinfo
        ))
    
    
    
    #dynamo更新
    print("dynamo更新")
    with table.batch_writer() as batch:
        for n in range(len(favoriteupds)):
            r = favoriteupds[n]

            wkobj = {
                "id": r.id,
                "userid": r.userid,
                "imageinfo": {
                    "datapaths": r.imageinfo.datapaths,
                    "position": r.imageinfo.position,
                    "size": r.imageinfo.size,
                    "tag": r.imageinfo.tag
                }
            }
            
            
            batch.put_item(Item=wkobj)
        # for n in range(1):
        #     batch.put_item(Item=obj)
    
    print("終了------>")

    return favoriteupds

@app.put("/Favorites/{id}", response_model=ResponseFavorite)
def update_Favorite_item(id: str):
    """
    Favorite アイテムを更新する
    """
    # Favorite アップデート処理
    return {
	"id":id,
	"userid":"100001",
	"imageinfos":[
		{
			"datapaths":[
				"python.webp",
				"threeJS.png",
				"angular.png",
				"aws.png",
				"docker.png",
				"react.png"
			],
			"position":[0,0,0],
			"size":[1.5,1.5,1.5],
			"tag":"engineer"
		}
	]
}

@app.delete("/Favorites/{id}")
def delete_Favorite_item(id: str):
    """
    Favorite アイテムを削除する
    """
    # Favorite 削除処理
    return {
        "id": id,
        "name": "Favorite-1",
        "description": "hogehogehoge"
    }


handler = Mangum(app)