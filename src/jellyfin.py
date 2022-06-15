import requests
from src.functions import logger, search_mapping, str_to_bool, check_skip_logic, generate_library_guids_dict, future_thread_executor

class Jellyfin():
    def __init__(self, baseurl, token):
        self.baseurl = baseurl
        self.token = token
        self.session = requests.Session()

        if not self.baseurl:
            raise Exception("Jellyfin baseurl not set")

        if not self.token:
            raise Exception("Jellyfin token not set")

        self.users = self.get_users()


    def query(self, query, query_type):
        try:
            response = None

            headers = {
                "Accept": "application/json",
                "X-Emby-Token": self.token
            }
            if query_type == "get":
                response = self.session.get(self.baseurl + query, headers=headers)

            elif query_type == "post":
                authorization = (
                    'MediaBrowser , '
                    'Client="other", '
                    'Device="script", '
                    'DeviceId="script", '
                    'Version="0.0.0"'
                )
                headers["X-Emby-Authorization"] = authorization
                response = self.session.post(self.baseurl + query, headers=headers)

            return response.json()
        except Exception as e:
            logger(e, 2)
            logger(response, 2)

    def get_users(self):
        users = {}

        query = "/Users"
        response = self.query(query, "get")

        # If reponse is not empty
        if response:
            for user in response:
                users[user["Name"]] = user["Id"]

        return users

    def get_user_watched(self, user_name, user_id, library_type, library_id, library_title):
        user_watched = {}

        logger(f"Jellyfin: Generating watched for {user_name} in library {library_title}", 0)
        # Movies
        if library_type == "Movie":
            watched = self.query(f"/Users/{user_id}/Items?SortBy=SortName&SortOrder=Ascending&Recursive=true&ParentId={library_id}&Filters=IsPlayed&Fields=ItemCounts,ProviderIds", "get")
            for movie in watched["Items"]:
                if movie["UserData"]["Played"] == True:
                    if movie["ProviderIds"]:
                        if user_name not in user_watched:
                            user_watched[user_name] = {}
                        if library_title not in user_watched[user_name]:
                            user_watched[user_name][library_title] = []
                        # Lowercase movie["ProviderIds"] keys
                        movie["ProviderIds"] = {k.lower(): v for k, v in movie["ProviderIds"].items()}
                        user_watched[user_name][library_title].append(movie["ProviderIds"])

        # TV Shows
        if library_type == "Episode":
            watched = self.query(f"/Users/{user_id}/Items?SortBy=SortName&SortOrder=Ascending&Recursive=true&ParentId={library_id}&Fields=ItemCounts,ProviderIds", "get")
            watched_shows = [x for x in watched["Items"] if x["Type"] == "Series"]

            for show in watched_shows:
                show_guids = {k.lower(): v for k, v in show["ProviderIds"].items()}
                show_guids["title"] = show["Name"]
                show_guids = frozenset(show_guids.items())
                seasons = self.query(f"/Shows/{show['Id']}/Seasons?userId={user_id}&Fields=ItemCounts,ProviderIds", "get")
                if len(seasons["Items"]) > 0:
                    for season in seasons["Items"]:
                        episodes = self.query(f"/Shows/{show['Id']}/Episodes?seasonId={season['Id']}&userId={user_id}&Fields=ItemCounts,ProviderIds", "get")
                        if len(episodes["Items"]) > 0:
                            for episode in episodes["Items"]:
                                if episode["UserData"]["Played"] == True:
                                    if episode["ProviderIds"]:
                                        if user_name not in user_watched:
                                            user_watched[user_name] = {}
                                        if library_title not in user_watched[user_name]:
                                            user_watched[user_name][library_title] = {}
                                        if show_guids not in user_watched[user_name][library_title]:
                                            user_watched[user_name][library_title][show_guids] = {}
                                        if season["Name"] not in user_watched[user_name][library_title][show_guids]:
                                            user_watched[user_name][library_title][show_guids][season["Name"]] = []

                                        # Lowercase episode["ProviderIds"] keys
                                        episode["ProviderIds"] = {k.lower(): v for k, v in episode["ProviderIds"].items()}
                                        user_watched[user_name][library_title][show_guids][season["Name"]].append(episode["ProviderIds"])

        return user_watched


    def get_watched(self, users, blacklist_library, whitelist_library, blacklist_library_type, whitelist_library_type, library_mapping=None):
        users_watched = {}
        args = []
        
        for user_name, user_id in users.items():
            # Get all libraries
            user_name = user_name.lower()

            libraries = self.query(f"/Users/{user_id}/Views", "get")["Items"]

            for library in libraries:
                library_title = library["Name"]
                library_id = library["Id"]
                watched = self.query(f"/Users/{user_id}/Items?SortBy=SortName&SortOrder=Ascending&Recursive=true&ParentId={library_id}&Filters=IsPlayed&limit=1", "get")

                if len(watched["Items"]) == 0:
                    logger(f"Jellyfin: No watched items found in library {library_title}", 1)
                    continue
                else:
                    library_type = watched["Items"][0]["Type"]

                skip_reason = check_skip_logic(library_title, library_type, blacklist_library, whitelist_library, blacklist_library_type, whitelist_library_type, library_mapping)

                if skip_reason:
                    logger(f"Jellyfin: Skipping library {library_title} {skip_reason}", 1)
                    continue

                args.append([self.get_user_watched, user_name, user_id, library_type, library_id, library_title])

        for user_watched in future_thread_executor(args):
            users_watched.update(user_watched)

        return users_watched


    def update_user_watched(self, user, user_id, library, library_id, videos, dryrun):
        logger(f"Jellyfin: Updating watched for {user} in library {library}", 1)
        library_search = self.query(f"/Users/{user_id}/Items?SortBy=SortName&SortOrder=Ascending&Recursive=true&ParentId={library_id}&limit=1", "get")
        library_type = library_search["Items"][0]["Type"]

        # Movies
        if library_type == "Movie":
            _, _, videos_movies_ids = generate_library_guids_dict(videos, 2)

            jellyfin_search = self.query(f"/Users/{user_id}/Items?SortBy=SortName&SortOrder=Ascending&Recursive=false&ParentId={library_id}&isPlayed=false&Fields=ItemCounts,ProviderIds", "get")
            for jellyfin_video in jellyfin_search["Items"]:
                if str_to_bool(jellyfin_video["UserData"]["Played"]) == False:
                    jellyfin_video_id = jellyfin_video["Id"]

                    for movie_provider_source, movie_provider_id in jellyfin_video["ProviderIds"].items():
                        if movie_provider_source.lower() in videos_movies_ids:
                            if movie_provider_id.lower() in videos_movies_ids[movie_provider_source.lower()]:
                                msg = f"{jellyfin_video['Name']} as watched for {user} in {library} for Jellyfin"
                                if not dryrun:
                                    logger(f"Marking {msg}", 0)
                                    self.query(f"/Users/{user_id}/PlayedItems/{jellyfin_video_id}", "post")
                                else:
                                    logger(f"Dryrun {msg}", 0)
                                break

        # TV Shows
        if library_type == "Episode":
            videos_shows_ids, videos_episode_ids, _ = generate_library_guids_dict(videos, 3)

            jellyfin_search = self.query(f"/Users/{user_id}/Items?SortBy=SortName&SortOrder=Ascending&Recursive=false&ParentId={library_id}&isPlayed=false&Fields=ItemCounts,ProviderIds", "get")
            jellyfin_shows = [x for x in jellyfin_search["Items"]]

            for jellyfin_show in jellyfin_shows:
                show_found = False
                for show_provider_source, show_provider_id in jellyfin_show["ProviderIds"].items():
                    if show_provider_source.lower() in videos_shows_ids:
                        if show_provider_id.lower() in videos_shows_ids[show_provider_source.lower()]:
                            show_found = True
                            jellyfin_show_id = jellyfin_show["Id"]
                            jellyfin_episodes = self.query(f"/Shows/{jellyfin_show_id}/Episodes?userId={user_id}&Fields=ItemCounts,ProviderIds", "get")
                            for jellyfin_episode in jellyfin_episodes["Items"]:
                                if str_to_bool(jellyfin_episode["UserData"]["Played"]) == False:
                                    jellyfin_episode_id = jellyfin_episode["Id"]

                                    for episode_provider_source, episode_provider_id in jellyfin_episode["ProviderIds"].items():
                                        if episode_provider_source.lower() in videos_episode_ids:
                                            if episode_provider_id.lower() in videos_episode_ids[episode_provider_source.lower()]:
                                                msg = f"{jellyfin_episode['SeriesName']} {jellyfin_episode['SeasonName']} Episode {jellyfin_episode['IndexNumber']} {jellyfin_episode['Name']} as watched for {user} in {library} for Jellyfin"
                                                if not dryrun:
                                                    logger(f"Marked {msg}", 0)
                                                    self.query(f"/Users/{user_id}/PlayedItems/{jellyfin_episode_id}", "post")
                                                else:
                                                    logger(f"Dryrun {msg}", 0)
                                                break

                    if show_found:
                        break


    def update_watched(self, watched_list, user_mapping=None, library_mapping=None, dryrun=False):
        args = []
        for user, libraries in watched_list.items():
            user_other = None
            if user_mapping:
                if user in user_mapping.keys():
                    user_other = user_mapping[user]
                elif user in user_mapping.values():
                    user_other = search_mapping(user_mapping, user)

            user_id = None
            for key in self.users.keys():
                if user.lower() == key.lower():
                    user_id = self.users[key]
                    break
                elif user_other and user_other.lower() == key.lower():
                    user_id = self.users[key]
                    break

            if not user_id:
                logger(f"{user} {user_other} not found in Jellyfin", 2)
                continue

            jellyfin_libraries = self.query(f"/Users/{user_id}/Views", "get")["Items"]

            for library, videos in libraries.items():
                library_other = None
                if library_mapping:
                    if library in library_mapping.keys():
                        library_other = library_mapping[library]
                    elif library in library_mapping.values():
                        library_other = search_mapping(library_mapping, library)


                if library.lower() not in [x["Name"].lower() for x in jellyfin_libraries]:
                    if library_other and library_other.lower() in [x["Name"].lower() for x in jellyfin_libraries]:
                        logger(f"Plex: Library {library} not found, but {library_other} found, using {library_other}", 1)
                        library = library_other
                    else:
                        logger(f"Library {library} {library_other} not found in Plex library list", 2)
                        continue


                library_id = None
                for jellyfin_library in jellyfin_libraries:
                    if jellyfin_library["Name"] == library:
                        library_id = jellyfin_library["Id"]
                        continue

                if library_id:
                    args.append([self.update_user_watched, user, user_id, library, library_id, videos, dryrun])

        future_thread_executor(args)
