import requests
import time
import os
from dotenv import load_dotenv

load_dotenv(override=True)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API = "https://api.github.com"

def github_request(url, token=None, params=None):
    """统一 GitHub API 请求封装"""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 403 and "X-RateLimit-Remaining" in response.headers and response.headers["X-RateLimit-Remaining"] == "0":
        reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
        wait_sec = max(0, reset_time - time.time()) + 1
        print(f"Rate limit reached. Waiting {wait_sec:.0f} seconds...")
        time.sleep(wait_sec)
        return github_request(url, token, params)
    elif response.status_code != 200:
        raise Exception(f"GitHub API error {response.status_code}: {response.text}")
    return response.json()


def get_repo_info(owner, repo, token=None):
    """获取仓库详细信息"""
    url = f"{GITHUB_API}/repos/{owner}/{repo}"
    data = github_request(url, token)
    return {
        "name": data["name"],
        "full_name": data["full_name"],
        "owner": data["owner"]["login"],
        "description": data.get("description"),
        "language": data.get("language"),
        "topics": data.get("topics", []),
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "watchers": data.get("watchers_count"),
        "license": data["license"]["name"] if data.get("license") else None,
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "pushed_at": data.get("pushed_at"),
        "html_url": data.get("html_url"),
    }


def get_repo_contributors(owner, repo, token=None, limit=None):
    """获取仓库的贡献者"""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contributors"
    params = {"per_page": 100}
    contributors = []
    while url:
        data = github_request(url, token, params)
        contributors.extend(data)
        if limit and len(contributors) >= limit:
            break
        # 翻页
        link = requests.get(url, headers={"Authorization": f"Bearer {token}" if token else None}).links
        url = link["next"]["url"] if "next" in link else None
    return [
        {"login": c["login"], "contributions": c["contributions"], "url": c["url"]}
        for c in contributors[:limit] if "login" in c
    ]


def get_user_profile(username, token=None):
    """获取用户个人信息"""
    url = f"{GITHUB_API}/users/{username}"
    data = github_request(url, token)
    return {
        "login": data["login"],
        "name": data.get("name"),
        "company": data.get("company"),
        "location": data.get("location"),
        "bio": data.get("bio"),
        "followers": data.get("followers"),
        "following": data.get("following"),
        "public_repos": data.get("public_repos"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "html_url": data.get("html_url"),
    }


def get_user_repos(username, token=None, limit=10):
    """获取用户公开仓库（按 star 数排序）"""
    url = f"{GITHUB_API}/users/{username}/repos"
    params = {"per_page": limit, "sort": "updated"}
    repos = github_request(url, token, params)
    return [
        {
            "name": r["name"],
            "full_name": r["full_name"],
            "stargazers_count": r["stargazers_count"],
            "language": r["language"],
            "html_url": r["html_url"],
            "updated_at": r["updated_at"],
        }
        for r in repos
    ]


def aggregate_github_project(owner, repo, token=None, contributor_limit=5, user_repo_limit=5):
    """主函数：聚合项目与贡献者数据"""
    result = {"repository": get_repo_info(owner, repo, token)}
    contributors = get_repo_contributors(owner, repo, token, limit=contributor_limit)
    enriched_contributors = []

    for c in contributors:
        username = c["login"]
        print(f"Fetching contributor: {username}")
        profile = get_user_profile(username, token)
        user_repos = get_user_repos(username, token, user_repo_limit)
        enriched_contributors.append({
            "profile": profile,
            "contributions": c["contributions"],
            "repos": user_repos
        })
        time.sleep(1)  # 防止API速率过快

    result["contributors"] = enriched_contributors
    return result


# === 示例调用 ===
if __name__ == "__main__":
    TOKEN = os.getenv("GITHUB_TOKEN")
    OWNER = "eracle"
    REPO = "linkedin"

    data = aggregate_github_project(OWNER, REPO, TOKEN, contributor_limit=3, user_repo_limit=3)

    import json
    with open("github_project_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("✅ 数据已保存到 github_project_data.json")
