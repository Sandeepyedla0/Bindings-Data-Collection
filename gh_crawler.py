import requests
import sys
import time
import subprocess
import os

# Insert GitHub API token here
headers = {"Authorization": "Bearer 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"}

# Constants & language argument
NUM_REPOS = 20
MIN_STARS = 50	
LAST_ACTIVE = '2020-01-01'
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
          search(query: "language:{LANGUAGE} fork:false pushed:>{LAST_ACTIVE} sort:stars stars:<{max_stars}", type: REPOSITORY, first: 10 {', after: "' + end_cursor + '"' if end_cursor else ''}) {{
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
                success = True
        if not success:
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
    edges = content['data']['search']['edges']
    repositories_with_stars = []
    for edge in edges:
        if not edge['node']['isPrivate'] and not edge['node']['isDisabled'] and not edge['node']['isLocked']:
            repository = edge['node']['url']
            star_count = edge['node']['stargazers']['totalCount']
            if star_count < MIN_STARS:
                return repositories_with_stars, True
            if check_file_content(repository):
                print('Found PYBIND11_MODULE in', repository)
                repositories_with_stars.append((repository, star_count))
            else:
                print('PYBIND11_MODULE not found in', repository)
    return repositories_with_stars, False

def check_file_content(repository_url, download_directory):
    pybind_flag = 0
    valid_extensions = ['.cpp', '.cxx', '.cc', '.C', '.c++']

    # Get the repository name from the URL
    repository_name = repository_url.split("/")[-1]

    # Create a path for the cloned repository
    cloned_repository_path = os.path.join(download_directory, repository_name)

    # Clone the repository into the new path
    subprocess.run(["git", "clone", "--depth", "1", repository_url, cloned_repository_path])

    print(cloned_repository_path)
    if os.path.exists(cloned_repository_path):
        print(f"The directory '{cloned_repository_path}' already exists.")

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
                            print("Found PYBIND11_MODULE in", file_path)
                    except UnicodeDecodeError:
                        print(f"UnicodeDecodeError while reading {file_path}. Skipping this file.")
                    except Exception as e:
                        print(f"Error while processing file: {str(e)}")

    if pybind_flag == 1:
        return True
    else:
        subprocess.run(["rm", "-rf", cloned_repository_path])
        return False

if __name__ == '__main__':
    main()
