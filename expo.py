import requests
import sys
import time

import shutil
import subprocess
import base64

# Insert GitHub API token here, in place of *TOKEN*.
access_token = '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'
headers = {"Authorization": f"token {access_token}"}

# Constants & language argument.
NUM_REPOS = 10
MIN_STARS = 5
LAST_ACTIVE = '2015-01-01'
LANGUAGE = "C++" if len(sys.argv) <= 1 else sys.argv[1]  # Default to Java, if none passed

# Search string to look for in repository files
SEARCH_STRING = "PYBIND11_MODULE"

def main():
    repositories = set()  # Keep track of a set of repositories seen to avoid duplicate entries across pages.
    next_max_stars = 1_000_000_000  # Initialize to a very high value.
    with open(f'TopLists/{LANGUAGE}-top-repos.txt', 'w') as f:
        while len(repositories) < NUM_REPOS:
            results = run_query(next_max_stars)  # Get the next set of pages.
            if not results:
                break
            new_repositories = [repository for repository, _ in results]
            next_max_stars = min([stars for _, stars in results])

            # If a query returns no new repositories, drop it.
            if len(repositories | set(new_repositories)) == len(repositories):
                break
            for repository, stars in sorted(results, key=lambda e: e[1], reverse=True):
                if repository not in repositories:
                    repositories.add(repository)
                    f.write(f'{stars}\t{repository}\n')
            f.flush()
            print(f'Collected {len(repositories):,} repositories so far; lowest number of stars: {next_max_stars:,}')


def run_query(max_stars):
    end_cursor = None  # Used to track pagination.
    repositories = set()

    while end_cursor != "":
        # Extracts non-fork, recently active repositories in the provided language, in groups of 100.
        # Leaves placeholders for maximum stars and page cursor. The former allows us to retrieve more than 1,000 repositories
        # by repeatedly lowering the bar.
        query = f"""
        {{
          search(query: "language:{LANGUAGE} fork:false pushed:>{LAST_ACTIVE} sort:stars stars:<{max_stars}", type: REPOSITORY, first: 300 {', after: "' + end_cursor + '"' if end_cursor else ''}) {{
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
        print(f'  Retrieving next page; {len(repositories)} repositories in this batch so far.')
        # Attempt a query up to three times, pausing when a query limit is hit.
        attempts = 0
        success = False
        while not success and attempts < 3:
            request = requests.post('https://api.github.com/graphql', json={'query': query}, headers=headers)
            content = request.json()
            if 'data' not in content or 'search' not in content['data']:
                # If this is simply a signal to pause querying, wait two minutes.
                if 'message' in content and 'wait' in content['message']:
                    attempts += 1
                    time.sleep(120)
                # Otherwise, assume we've hit the end of the stream.
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

# def find_pybind_lib(file_content):
#     if re.search(r'#include\s*<pybind11/', file_content):
#         # pattern = r'#include\s*["<](?!pybind11/)(.*?\.(h|hpp))[">]'
#         # header_files = re.findall(pattern, file_content)
#         return True
#     return False

def find_pybind_lib(file_content):
    if SEARCH_STRING in file_content:
        print('Pybind module found')
        return True
    return False


def get_repositories(content):
    edges = content['data']['search']['edges']
    repositories_with_stars = []
    for edge in edges:
        if edge['node']['isPrivate'] is False and edge['node']['isDisabled'] is False and edge['node']['isLocked'] is False:
            repository = edge['node']['url']
            star_count = edge['node']['stargazers']['totalCount']
            # Extract the owner and repository name from the GitHub URL
            repo_name = repository.split("/")[-1]
            download_directory = "downloaded_files"

            # Create the download directory if it doesn't exist
            if not os.path.exists(download_directory):
                os.makedirs(download_directory)
            if star_count < MIN_STARS:
                return repositories_with_stars, True
            elif process_directory_contents(repository_url, "", download_directory):
                    print("process_directory_contents_success")
                    repositories_with_stars.append((repository, star_count))
            else:
                print("process_directory_contents false")
    print("is done: False")
    return repositories_with_stars, False

def process_directory_contents(repo_url, path):
    # Extract the repository name from the URL
    repo_name = repo_url.split('/')[-1]
    # Create a subdirectory with the repository name
    save_directory = os.path.join(parent_directory, repo_name)
    # Clone the repository into the specified directory
    clone_command = ["git", "clone", repo_url, save_directory]
    subprocess.run(clone_command, check=True)
    pybind_found = False  # Initialize the pybind_found flag
    for root, _, files_list in os.walk(save_directory):
        for file_name in files_list:
            file_path = os.path.join(root, file_name)
            if file_name.endswith(".cpp"):
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                    file_content = file.read()
                    pybind_flag = find_pybind_lib(file_content)
                    if pybind_flag:
                        pybind_found = True  # Set pybind_found to True if a file with Pybind 11 is found
                        print(f"Pybind 11 used in: {file_path}")
                        return True
            else:
                pass

    # if not pybind_found:
    #     print(f"No Pybind 11 modules found in {repo_name} repository. Deleting the repository...")
    #     shutil.rmtree(save_directory)
    return False
    # else:
    #     print(f"Pybind 11 modules found in {repo_name} repository.")


if __name__ == '__main__':
    main()
