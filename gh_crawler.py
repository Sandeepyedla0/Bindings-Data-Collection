import requests
import sys
import time
import subprocess
import os
import pandas as pd
import csv

# GitHub API token

headers = {"Authorization": "Bearer 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"}
dataset = []

# Constants & language argument
NUM_REPOS = 2
MIN_STARS = 50
NUM_REPOS_CLONED = 0
num_pybind_repos_cloned = 0
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
    end_cursor = None  # track pagination
    repositories = set()

    while end_cursor != "":
        # Extracts non-fork, recently active repositories in the provided language, in groups of 100

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

def write_dataset_to_csv(dataset):
    fieldnames = ['repo_owner_name', 'repo_name', 'repository_url','star_count', 'fork_count', 'pushedat','binding_file_path']
    with open('meta_data.csv', 'a', newline='',encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writerows(dataset)


def get_repositories(content):
    #print("In get_repo")
    edges = content['data']['search']['edges']
    repositories_with_stars = []
    fieldnames = ['repo_owner_name', 'repo_name', 'repository_url','star_count', 'fork_count', 'pushedat','binding_file_path']
    dataset1=[]
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
            download_directory = "test_output"
            # Create the download directory if it doesn't exist
            if not os.path.exists(download_directory):
                os.makedirs(download_directory)
            repo_check_flag, bindings_path, already_exists_flag = check_file_content(repository, download_directory)
            if repo_check_flag:
                if already_exists_flag == 1:
                    with open('meta_data.csv', 'r',encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile,fieldnames=fieldnames)
                        dataset = list(reader)
                    for i, data in enumerate(dataset):
                        if data['repository_url'] == repository:
                            dataset[i]['fork_count'] = forks_count
                            dataset[i]['pushedat'] = pushed_at
                            break
                    # Save the modified data back to the CSV file
                    with open('meta_data.csv', 'w', newline='',encoding='utf-8') as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames) 
                        # Write the modified data
                        writer.writerows(dataset)
                else:
                    dataset1.append({
                        'repo_owner_name': owner_name,
                        "repo_name": repository_name,
                        "repository_url": repository,
                        "star_count": star_count,
                        "fork_count": forks_count,
                        "pushedat": pushed_at,
                        "binding_file_path": bindings_path
                    })
                    with open("pybind_visited_repos.txt", "r", encoding='utf-8') as f:
                        visited_repos = f.read().splitlines()


                    if repository not in visited_repos:
                        write_dataset_to_csv(dataset1)
                        repositories_with_stars.append((repository, star_count))
                        with open("pybind_visited_repos.txt", "a", encoding='utf-8') as f:
                            f.write(f"{repository}\n")

                
        if(num_pybind_repos_cloned)>2:
            return repositories_with_stars, True
    
    return repositories_with_stars, False

def check_file_content(repository, download_directory):  # Changed repository_url to repository
    #print("In check_file_content")
    pybind_flag = 0
    valid_extensions = ['.cpp', '.cxx', '.cc', '.C', '.c++','.h', '.hh', '.h++', '.hxx','.hpp','.H']
    bindings_path = []
    # Get the repository name from the URL
    repository_name = repository.split("/")[-1]
    already_exists_flag = 0


    # Create a path for the cloned repository
    cloned_repository_path = os.path.join(download_directory, repository_name)
    if os.path.exists(cloned_repository_path):
        print(f"The directory '{cloned_repository_path}' already exists in test_output.")
        already_exists_flag=1
    else:
        with open("nonpybind_visited_repositories.txt", "r", encoding='utf-8') as f:
            visited_repos = f.read().splitlines()
        if repository in visited_repos:
            print("Repository URL already in nonpybind_visited_repositories.txt:", repository)
            return False,[], already_exists_flag
        # Clone the repository into the new path
        else:
            subprocess.run(["git", "clone", "--depth", "1", repository, cloned_repository_path])
            global NUM_REPOS_CLONED
            NUM_REPOS_CLONED += 1
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

    if already_exists_flag == 1:
        print("File already in testoutput: ",repository)
        return True, bindings_path, already_exists_flag
    elif pybind_flag==1:
        return True, bindings_path, already_exists_flag
    else:
        with open("nonpybind_visited_repositories.txt", "r", encoding='utf-8') as f:
            visited_repos = f.read().splitlines()
        if repository not in visited_repos:
            with open("nonpybind_visited_repositories.txt", "a", encoding='utf-8') as f:
                f.write(f"{repository}\n")                                                                         
        subprocess.run(["rm", "-rf", cloned_repository_path])
        return False, [], already_exists_flag

if __name__ == '__main__':
    start_time = time.time()
    main()
    print(" ******* Number of repos cloned ******* :",NUM_REPOS_CLONED)
    end_time = time.time()
    execution_time = (end_time - start_time)
    print("Script Excecution time : ",execution_time)
    with open("execution_time.txt", "w", encoding='utf-8') as text_file:
        text_file.write("Script Execution time: " + str(execution_time))
