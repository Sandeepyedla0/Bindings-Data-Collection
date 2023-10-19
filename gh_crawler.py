import requests
import sys
import time
import subprocess
import os
import pandas as pd

# GitHub API token

headers = {"Authorization": "Bearer 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 "}
dataset = []

# Constants & language argument
NUM_REPOS = 100
MIN_STARS = 50
NUM_REPOS_CLONED = 0
#num_pybind_repos_cloned = 0
LAST_ACTIVE = '2015-01-01'
LANGUAGE = "C++" if len(sys.argv) <= 1 else sys.argv[1]  # Default to C++ if none passed

def main():
    repositories = set()  # Keep track of a set of repositories seen to avoid duplicate entries across pages
    next_max_stars = 1_000_000_000  # Initialize to a very high value
    with open(f'TopLists/{LANGUAGE}-top-repos.txt', 'w') as f:
        while len(repositories) < NUM_REPOS:
            results = run_query(next_max_stars)  # Get the next set of pages
            if not results:
                break
            new_repositories = [repository for repository, _ in results]
            next_max_stars = min([stars for _, stars in results])

            # If a query returns no new repositories, drop it
            if len(repositories | set(new_repositories)) == len(repositories):
                break
            for repository, stars in sorted(results, key=lambda e: e[1], reverse=True):
                if repository not in repositories:
                    repositories.add(repository)
                    f.write(f'{stars}\t{repository}\n')
            f.flush()
            print(f'Collected {len(repositories):,} repositories so far; lowest number of stars: {next_max_stars:,}')

def run_query(max_stars):
    end_cursor = None  # Used to track pagination
    repositories = set()

    while end_cursor != "":
        # Extracts non-fork, recently active repositories in the provided language, in groups of 100
        # Leaves placeholders for maximum stars and page cursor. The former allows us to retrieve more than 1,000 repositories
        # by repeatedly lowering the bar
        query = f"""
        {{
            search(query: "language:{LANGUAGE} fork:false pushed:>{LAST_ACTIVE} sort:stars stars:<{max_stars}", type: REPOSITORY, first: 100 {', after: "' + end_cursor + '"' if end_cursor else ''}) {{
                edges {{
                    node {{
                        ... on Repository {{
                            url
                            isPrivate
                            isDisabled
                            isLocked
                            stargazers {{
                                totalCount
                            }}
                            forks {{
                                totalCount
                            }}
                            pushedAt
                        }}
                    }}
                }}
                pageInfo {{
                    hasNextPage
                    endCursor
                }}
            }}
        }}
"""


        print(f'Retrieving next page; {len(repositories)} repositories in this batch so far')
        # Attempt a query up to three times, pausing when a query limit is hit
        attempts = 0
        success = False
        while not success and attempts < 3:
            request = requests.post('https://api.github.com/graphql', json={'query': query}, headers=headers)
            content = request.json()
            if 'data' not in content or 'search' not in content['data']:
                # If this is simply a signal to pause querying, wait two minutes
                if 'message' in content and 'wait' in content['message']:
                    attempts += 1
                    time.sleep(120)
                # Otherwise, assume we've hit the end of the stream
                else:
                    break
            else:
                print('success==True')
                success = True
        if not success:
            print("success==False")
            break
        end_cursor = get_end_cursor(content)
        new_repositories, is_done = get_repositories(content)
        repositories.update(new_repositories)
        if len(repositories) > NUM_REPOS or is_done:
            break
    return repositories

def get_end_cursor(content):
    page_info = content['data']['search']['pageInfo']
    has_next_page = page_info['hasNextPage']
    if has_next_page:
        return page_info['endCursor']
    return ""

def get_repositories(content):
    #print("In get_repo")
    edges = content['data']['search']['edges']
    repositories_with_stars = []
    
    for edge in edges:
        if not edge['node']['isPrivate'] and not edge['node']['isDisabled'] and not edge['node']['isLocked']:
            repository = edge['node']['url']
            star_count = edge['node']['stargazers']['totalCount']
            forks_count = edge['node']['forks']['totalCount']
            pushed_at = edge['node']['pushedAt']
            repository_name = repository.split("/")[-1]
            owner_name = repository.split("/")[-2]
            if star_count < MIN_STARS:
                return repositories_with_stars, True
            print('pushed_at',pushed_at)
            download_directory = "test_output"
            # Create the download directory if it doesn't exist
            if not os.path.exists(download_directory):
                os.makedirs(download_directory)
            repo_check_flag, bindings_path = check_file_content(repository, download_directory)
            if repo_check_flag:  
                print('Found PYBIND11_MODULE in', repository)
                dataset.append({
                        #"binding_file": file_name,
                        'repo_owner_name': owner_name,
                        "repo_name": repository_name,
                        "repository_URL":repository,
                        "binding_file_path": bindings_path,
                        "star_count": star_count,
                        "fork_Count": forks_count,
                        "PushedAT": pushed_at
                    })
                repositories_with_stars.append((repository, star_count))
            #     global num_pybind_repos_cloned 
            #     num_pybind_repos_cloned+=1
            # if(num_pybind_repos_cloned)>=3:
            #     return repositories_with_stars, True
            

    return repositories_with_stars, False

def check_file_content(repository, download_directory):  # Changed repository_url to repository
    #print("In check_file_content")
    pybind_flag = 0
    valid_extensions = ['.cpp', '.cxx', '.cc', '.C', '.c++','.h', '.hh', '.h++', '.hxx','.hpp','.H']
    bindings_path = []
    # Get the repository name from the URL
    repository_name = repository.split("/")[-1]
    
    # Create a path for the cloned repository
    cloned_repository_path = os.path.join(download_directory, repository_name)
    # if os.path.exists(cloned_repository_path):
    #     print(f"The directory '{cloned_repository_path}' already exists.")

    # Clone the repository into the new path
    subprocess.run(["git", "clone", "--depth", "1", repository, cloned_repository_path])  
    global NUM_REPOS_CLONED  
    NUM_REPOS_CLONED += 1
    #print(cloned_repository_path)
    

    for root, _, files in os.walk(cloned_repository_path):
        for file in files:
            file_path = os.path.join(root, file)
            _, file_extension = os.path.splitext(file_path)

            if file_extension in valid_extensions:
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            file_content = f.read()
                        if "PYBIND11_MODULE" in file_content:
                            pybind_flag = 1
                            bindings_path.append(file_path)
                            print("Found PYBIND11_MODULE in", file_path)
                    except UnicodeDecodeError:
                        print(f"UnicodeDecodeError while reading {file_path}. Skipping this file.")
                    except Exception as e:
                        print(f"Error while processing file: {str(e)}")

    if pybind_flag == 1:
        return True, bindings_path
    else:
        subprocess.run(["rm", "-rf", cloned_repository_path])
        return False, []

if __name__ == '__main__':
    start_time = time.time()
    main()
    print(" ******* Number of repos cloned ******* :",f)
    print("*****Dataset creation********")
    df = pd.DataFrame(dataset)
    df.to_csv("meta_data.csv")
    end_time = time.time()
    execution_time = (end_time - start_time)//3600
    print("Script Excecution time : ",execution_time)
    with open("execution_time.txt", "w") as text_file:
        text_file.write("Script Execution time: " + str(execution_time))
