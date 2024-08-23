import os
from os.path import dirname, join
from time import sleep

import requests
from dotenv import load_dotenv, set_key
from utils import oauth

dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)

AL_DATA = {}
if (os.environ.get("ANILIST_TOKEN") is None) or (os.environ.get("ANILIST_TOKEN") == ""):
    AL_DATA = {
        "ANILIST_CLIENT_ID": os.environ.get("ANILIST_CLIENT_ID"),
        "ANILIST_CLIENT_SECRET": os.environ.get("ANILIST_CLIENT_SECRET"),
        "ANILIST_REDIRECT_URI": os.environ.get("ANILIST_REDIRECT_URI"),
    }
    AL_DATA["ANILIST_TOKEN"] = oauth.GET_AL_TOKEN(AL_DATA)["access_token"]
    set_key(dotenv_path, "ANILIST_TOKEN", AL_DATA["ANILIST_TOKEN"], quote_mode="always")
    print("AL Token has been saved on dotenv file")
else:
    AL_DATA["ANILIST_TOKEN"] = os.environ.get("ANILIST_TOKEN")


def run_query(query, variables):
    response = requests.post(
        "https://graphql.anilist.co",
        json={"query": query, "variables": variables},
        headers={
            "content-type": "application/json",
            "authorization": "Bearer " + AL_DATA["ANILIST_TOKEN"],
        },
    )
    if response.status_code == 200:
        return response.json()["data"]
    elif response.status_code == 429:
        print("Too many requests! Waiting 60 seconds to continue...")
        sleep(60)
    else:
        raise Exception("AniList query failed!")


def query_typein():
    if (os.environ.get("QUERY_OPTIONS") is None) or (
        os.environ.get("QUERY_OPTIONS") == ""
    ):
        q_typein = "TEXT, ANIME_LIST, MANGA_LIST, MESSAGE"
        set_key(dotenv_path, "QUERY_OPTIONS", q_typein, quote_mode="always")
    else:
        q_typein = os.environ.get("QUERY_OPTIONS")
    return q_typein.split(", ")


def main():
    ANILIST_USERNAME = input("AniLikerV2 by anas1412 is a fork of AniLiker by taichikuji\nFor more information check the following repo:\nhttps://github.com/anas1412/AniLikerV2\n\nInput an AniList username!\n> ")

    query = """
        query ($username: String) {
          User (name: $username) {
            id
          }
        }
    """

    variables = {"username": ANILIST_USERNAME}

    user_id = run_query(query, variables)["User"]["id"]

    npage = 1
    while npage > 0:
        query = """
      query ($user_id: Int, $page: Int, $perPage: Int, $q_options: [ActivityType]) {
              Page (page: $page, perPage: $perPage) {
                pageInfo {
                    hasNextPage
                  }
                activities (userId: $user_id, sort: ID_DESC, type_in: $q_options) {
                    ... on ListActivity {
                      id
                      isLiked
                      status
                      media {
                        title {
                          userPreferred
                        }
                        type
                      }
                  }
                  ... on TextActivity {
                      id
                      isLiked
                      text
                  }
                  ... on MessageActivity {
                    id
                    isLiked
                    message
                  }
                }
              }
            }
      """

        variables = {
            "user_id": user_id,
            "page": npage,
            "perPage": 30,
            "q_options": query_typein(),
        }
        page = run_query(query, variables)["Page"]
        activity = page["activities"]
        pageInfo = page["pageInfo"]["hasNextPage"]

        for value in activity:
            if not value["isLiked"]:
                if "status" in value:  # ListActivity
                    print(f"Activity Type: List Activity - {value['media']['type']}")
                    print(f"Title: {value['media']['title']['userPreferred']}")
                    print(f"Status: {value['status']}")
                elif "text" in value:  # TextActivity
                    print("Activity Type: Text Activity")
                    print(f"Text: {value['text'][:50]}...")  # Print first 50 characters
                elif "message" in value:  # MessageActivity
                    print("Activity Type: Message Activity")
                    print(f"Message: {value['message'][:50]}...")  # Print first 50 characters
                
                query = """
          mutation ($id: Int) {
            ToggleLikeV2(id: $id, type: ACTIVITY) {
              __typename
            }
          }
        """
                variables = {"id": value["id"]}

                # ToggleLikeV2 runs
                run_query(query, variables)
                print(f"Liked activity with ID: {value['id']}")
                print("--------------------")
        
        print(f"End of page, waiting 60 seconds to continue\nPage: {npage}")
        if pageInfo:
            npage = npage + 1
            sleep(60)
        else:
            npage = 0


if __name__ == "__main__":
    main()