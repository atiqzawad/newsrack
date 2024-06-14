#!/usr/bin/env python
__license__ = "GPL v3"

import json
from datetime import datetime
from urllib.parse import urljoin

from calibre.web.feeds.news import BasicNewsRecipe, prefixed_classes


class ScientificAmerican(BasicNewsRecipe):
    title = "Scientific American"
    description = "Popular Science. Monthly magazine. Should be downloaded around the middle of each month."
    category = "science"
    __author__ = "Kovid Goyal"
    no_stylesheets = True
    language = "en"
    publisher = "Nature Publishing Group"
    remove_empty_feeds = True
    remove_javascript = True
    timefmt = " [%B %Y]"
    remove_attributes = ["height", "width"]
    masthead_url = (
        "https://static.scientificamerican.com/sciam/assets/Image/newsletter/salogo.png"
    )
    extra_css = """
        [class^="article_dek-"] { font-style:italic; color:#202020; }
        [class^="article_authors-"] {font-size:small; color:#202020; }
        [class^="article__image-"] { font-size:small; text-align:center; }
        [class^="lead_image-"] { font-size:small; text-align:center; }
        [class^="bio-"] { font-size:small; color:#404040; }
        em { color:#202020; }
    """

    needs_subscription = "optional"

    keep_only_tags = [
        prefixed_classes(
            'article_hed- article_dek- article_authors- lead_image- article__content- bio-'
        ),
    ]
    remove_tags = [
        dict(name=['button', 'svg', 'iframe', 'source'])
    ]

    def preprocess_html(self, soup):
        for fig in soup.findAll('figcaption'):
            for p in fig.findAll('p'):
                p.name = 'span'
        return soup

    def get_browser(self, *args):
        br = BasicNewsRecipe.get_browser(self)
        if self.username and self.password:
            br.open("https://www.scientificamerican.com/account/login/")
            br.select_form(predicate=lambda f: f.attrs.get("id") == "login")
            br["emailAddress"] = self.username
            br["password"] = self.password
            br.submit()
        return br

    def parse_index(self):
        # Get the cover, date and issue URL
        fp_soup = self.index_to_soup("https://www.scientificamerican.com")
        curr_issue_link = fp_soup.find(**prefixed_classes('latest_issue_links-'))
        if not curr_issue_link:
            self.abort_recipe_processing("Unable to find issue link")
        issue_url = 'https://www.scientificamerican.com' + curr_issue_link.a["href"]
        # for past editions https://www.scientificamerican.com/archive/issues/
        # issue_url = 'https://www.scientificamerican.com/issue/sa/2024/01-01/'
        soup = self.index_to_soup(issue_url)
        script = soup.find("script", id="__DATA__")
        if not script:
            self.abort_recipe_processing("Unable to find script")

        JSON = script.contents[0].split('JSON.parse(`')[1].replace("\\\\", "\\")
        data = json.JSONDecoder().raw_decode(JSON)[0]
        issue_info = (
            data
            .get("initialData", {})
            .get("issueData", {})
        )
        if not issue_info:
            self.abort_recipe_processing("Unable to find issue info")

        self.cover_url = issue_info["image_url"] + "?w=800"

        edition_date = datetime.strptime(issue_info["issue_date"], "%Y-%m-%d")
        self.timefmt = f" [{edition_date:%B %Y}]"

        feeds = {}
        for section in ("featured", "departments"):
            for article in issue_info.get("article_previews", {}).get(section, []):
                self.log('\t', article["title"])
                if section == "featured":
                    feed_name = "Features"
                else:
                    feed_name = article["category"]
                if feed_name not in feeds:
                    feeds[feed_name] = []
                feeds[feed_name].append(
                    {
                        "title": article["title"],
                        "url": urljoin(
                            "https://www.scientificamerican.com/article/",
                            article["slug"],
                        ),
                        "description": article["summary"],
                    }
                )

        return feeds.items()
        
