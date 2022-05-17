#!/usr/bin/env  python
# License: GPLv3 Copyright: 2008, Kovid Goyal <kovid at kovidgoyal.net>

# Modified from https://github.com/kovidgoyal/calibre/blob/a0cc6d6c68efe1e9e7479451aa9bfc4df0812bac/recipes/economist.recipe

try:
    from http.cookiejar import Cookie
except ImportError:
    from cookielib import Cookie

from datetime import datetime, timezone
import json
from html5_parser import parse
from lxml import etree

from calibre import replace_entities
from calibre.ebooks.BeautifulSoup import NavigableString, Tag
from calibre.utils.cleantext import clean_ascii_chars
from calibre.web.feeds.news import BasicNewsRecipe, classes

# For past editions, set date to, for example, '2020-11-28'
edition_date = None


def E(parent, name, text="", **attrs):
    ans = parent.makeelement(name, **attrs)
    ans.text = text
    parent.append(ans)
    return ans


def process_node(node, html_parent):
    ntype = node.get("type")
    if ntype == "tag":
        c = html_parent.makeelement(node["name"])
        c.attrib.update({k: v or "" for k, v in node.get("attribs", {}).items()})
        html_parent.append(c)
        for nc in node.get("children", ()):
            process_node(nc, c)
    elif ntype == "text":
        text = node.get("data")
        if text:
            text = replace_entities(text)
            if len(html_parent):
                t = html_parent[-1]
                t.tail = (t.tail or "") + text
            else:
                html_parent.text = (html_parent.text or "") + text


def load_article_from_json(raw, root):
    data = json.loads(raw)["props"]["pageProps"]["content"]

    # open('/t/raw.json', 'w').write(json.dumps(data, indent=2, sort_keys=True))
    if isinstance(data, list):
        data = data[0]

    body = root.xpath("//body")[0]
    for child in tuple(body):
        body.remove(child)
    article = E(body, "article")
    E(article, "h4", data["subheadline"], style="color: red; margin: 0")
    E(article, "h1", data["headline"], style="font-size: x-large")
    E(
        article,
        "div",
        data["description"] or data["subheadline"],
        style="font-style: italic; font-size: large; margin-bottom: 1rem;",
        id="subheadline",
    )
    E(
        article,
        "div",
        (data["datePublishedString"] or "")
        + (" | " if data["dateline"] else "")
        + (data["dateline"] or ""),
        style="margin-bottom: 1rem; ",
        datecreated=data["dateModified"],
    )
    main_image_url = (
        data.get("image", {}).get("main", {}).get("url", {}).get("canonical")
    )
    if main_image_url:
        div = E(article, "div")
        try:
            E(div, "img", src=main_image_url)
        except Exception:
            pass
    for node in data["text"]:
        process_node(node, article)


def new_tag(soup, name, attrs=()):
    impl = getattr(soup, "new_tag", None)
    if impl is not None:
        return impl(name, attrs=dict(attrs))
    return Tag(soup, name, attrs=attrs or None)


class NoArticles(Exception):
    pass


def process_url(url):
    if url.startswith("/"):
        url = "https://www.economist.com" + url
    return url


class Economist(BasicNewsRecipe):

    title = "The Economist"
    language = "en"

    __author__ = "Kovid Goyal"
    description = (
        "Global news and current affairs from a European"
        " perspective. Best downloaded on Friday mornings (GMT)"
    )
    extra_css = """
        .headline {font-size: x-large;}
        h2 { font-size: medium; font-weight: bold;  }
        h1 { font-size: large; font-weight: bold; }
        em.Bold {font-weight:bold;font-style:normal;}
        em.Italic {font-style:italic;}
        p.xhead {font-weight:bold;}
        .pullquote {
            float: right;
            font-size: larger;
            font-weight: bold;
            font-style: italic;
            page-break-inside:avoid;
            border-bottom: 3px solid black;
            border-top: 3px solid black;
            width: 228px;
            margin: 0px 0px 10px 15px;
            padding: 7px 0px 9px;
        }
        .flytitle-and-title__flytitle {
            display: block;
            font-size: smaller;
            color: red;
        }
        """
    oldest_article = 7.0
    resolve_internal_links = True
    remove_tags = [
        dict(
            name=[
                "script",
                "noscript",
                "title",
                "iframe",
                "cf_floatingcontent",
                "aside",
                "footer",
            ]
        ),
        dict(attrs={"aria-label": "Article Teaser"}),
        dict(
            attrs={
                "class": [
                    "dblClkTrk",
                    "ec-article-info",
                    "share_inline_header",
                    "related-items",
                    "main-content-container",
                    "ec-topic-widget",
                    "teaser",
                    "blog-post__bottom-panel-bottom",
                    "blog-post__comments-label",
                    "blog-post__foot-note",
                    "blog-post__sharebar",
                    "blog-post__bottom-panel",
                    "newsletter-form",
                    "share-links-header",
                    "teaser--wrapped",
                    "latest-updates-panel__container",
                    "latest-updates-panel__article-link",
                    "blog-post__section",
                ]
            }
        ),
        dict(
            attrs={
                "class": lambda x: x and "blog-post__siblings-list-aside" in x.split()
            }
        ),
        classes(
            "share-links-header teaser--wrapped latest-updates-panel__container"
            " latest-updates-panel__article-link blog-post__section newsletter-form blog-post__bottom-panel"
        ),
    ]
    keep_only_tags = [dict(name="article", id=lambda x: not x)]
    no_stylesheets = True
    remove_attributes = ["data-reactid", "width", "height"]
    # economist.com has started throttling after about 60% of the total has
    # downloaded with connection reset by peer (104) errors.
    # delay = 1
    simultaneous_downloads = 2  # doesn't seem throttled now 2022.04.15

    compress_news_images = True
    masthead_url = "https://www.economist.com/assets/the-economist-logo.png"
    scale_news_images = (800, 800)
    scale_news_images_to_device = False  # force img to be resized to scale_news_images
    pub_date = None

    needs_subscription = False

    def __init__(self, *args, **kwargs):
        BasicNewsRecipe.__init__(self, *args, **kwargs)
        if self.output_profile.short_name.startswith("kindle"):
            # Reduce image sizes to get file size below amazon's email
            # sending threshold
            self.web2disk_options.compress_news_images = True
            self.web2disk_options.compress_news_images_auto_size = 5
            self.log.warn(
                "Kindle Output profile being used, reducing image quality to keep file size below amazon email threshold"
            )

    def get_browser(self):
        br = BasicNewsRecipe.get_browser(self)
        # Add a cookie indicating we have accepted Economist's cookie
        # policy (needed when running from some European countries)
        ck = Cookie(
            version=0,
            name="notice_preferences",
            value="2:",
            port=None,
            port_specified=False,
            domain=".economist.com",
            domain_specified=False,
            domain_initial_dot=True,
            path="/",
            path_specified=False,
            secure=False,
            expires=None,
            discard=False,
            comment=None,
            comment_url=None,
            rest={"HttpOnly": None},
            rfc2109=False,
        )
        br.cookiejar.set_cookie(ck)
        br.set_handle_gzip(True)
        return br

    def preprocess_raw_html(self, raw, _):
        root = parse(raw)
        script = root.xpath('//script[@id="__NEXT_DATA__"]')
        if script:
            load_article_from_json(script[0].text, root)
        for div in root.xpath('//div[@class="lazy-image"]'):
            noscript = list(div.iter("noscript"))
            if noscript and noscript[0].text:
                img = list(parse(noscript[0].text).iter("img"))
                if img:
                    p = noscript[0].getparent()
                    idx = p.index(noscript[0])
                    p.insert(idx, p.makeelement("img", src=img[0].get("src")))
                    p.remove(noscript[0])
        for x in root.xpath(
            '//*[name()="script" or name()="style" or name()="source" or name()="meta"]'
        ):
            x.getparent().remove(x)
        raw = etree.tostring(root, encoding="unicode")
        return raw

    def populate_article_metadata(self, article, soup, first):
        els = soup.findAll(
            name=["span", "p"],
            attrs={"class": ["flytitle-and-title__title", "blog-post__rubric"]},
        )
        result = []
        for el in els[0:2]:
            if el is not None and el.contents:
                for descendant in el.contents:
                    if isinstance(descendant, NavigableString):
                        result.append(type("")(descendant))
        article.summary = ". ".join(result) + ("." if result else "")
        if not article.summary:
            # try another method
            sub = soup.find(id="subheadline")
            if sub:
                article.summary = sub.string
        article.text_summary = clean_ascii_chars(article.summary)
        div_date = soup.find(attrs={"datecreated": True})
        if div_date:
            date_published = datetime.strptime(
                div_date["datecreated"],
                "%Y-%m-%dT%H:%M:%SZ",
            ).replace(tzinfo=timezone.utc)
            if not self.pub_date or date_published > self.pub_date:
                self.pub_date = date_published
                self.title = f"Economist: {date_published:%-d %b, %Y}"

    def publication_date(self):
        # if edition_date:
        #     return parse_only_date(edition_date, as_utc=False)
        # return BasicNewsRecipe.publication_date(self)
        return self.pub_date

    def parse_index(self):
        if edition_date:
            url = "https://www.economist.com/weeklyedition/" + edition_date
            self.timefmt = " [" + edition_date + "]"
        else:
            url = "https://www.economist.com/printedition"
        raw = self.index_to_soup(url, raw=True)
        # with open('/t/raw.html', 'wb') as f:
        #     f.write(raw)
        soup = self.index_to_soup(raw)
        # nav = soup.find(attrs={'class':'navigation__wrapper'})
        # if nav is not None:
        #     a = nav.find('a', href=lambda x: x and '/printedition/' in x)
        #     if a is not None:
        #         self.log('Following nav link to current edition', a['href'])
        #         soup = self.index_to_soup(process_url(a['href']))
        ans = self.economist_parse_index(soup)
        if not ans:
            raise NoArticles(
                "Could not find any articles, either the "
                "economist.com server is having trouble and you should "
                "try later or the website format has changed and the "
                "recipe needs to be updated."
            )
        return ans

    def economist_parse_index(self, soup):
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if script_tag is not None:
            data = json.loads(script_tag.string)
            self.cover_url = data["props"]["pageProps"]["content"]["image"]["main"][
                "url"
            ]["canonical"]
            self.log("Got cover:", self.cover_url)

            # Example 2022-04-16T00:00:00Z
            date_published = datetime.strptime(
                data["props"]["pageProps"]["content"]["datePublished"],
                "%Y-%m-%dT%H:%M:%SZ",
            ).replace(tzinfo=timezone.utc)
            self.title = f"Economist: {date_published:%-d %b, %Y}"

        feeds = []
        for section in soup.findAll(**classes("layout-weekly-edition-section")):
            h2 = section.find("h2")
            secname = self.tag_to_string(h2)
            self.log(secname)
            articles = []
            for a in section.findAll(
                "a", href=True, **classes("headline-link weekly-edition-wtw__link")
            ):
                spans = a.findAll("span")
                if len(spans) == 2:
                    title = "{}: {}".format(*map(self.tag_to_string, spans))
                else:
                    title = self.tag_to_string(a)
                desc = ""
                desc_parent = a.findParent("div")
                if desc_parent is not None:
                    p = desc_parent.find(itemprop="description")
                    if p is not None:
                        desc = self.tag_to_string(p)
                articles.append(
                    {"title": title, "url": process_url(a["href"]), "description": desc}
                )
                self.log(" ", title, articles[-1]["url"], "\n   ", desc)
            if articles:
                feeds.append((secname, articles))
        return feeds

    def eco_find_image_tables(self, soup):
        for x in soup.findAll("table", align=["right", "center"]):
            if len(x.findAll("font")) in (1, 2) and len(x.findAll("img")) == 1:
                yield x

    def postprocess_html(self, soup, first):
        for img in soup.findAll("img", srcset=True):
            del img["srcset"]
        for table in list(self.eco_find_image_tables(soup)):
            caption = table.find("font")
            img = table.find("img")
            div = new_tag(soup, "div")
            div["style"] = "text-align:left;font-size:70%"
            ns = NavigableString(self.tag_to_string(caption))
            div.insert(0, ns)
            div.insert(1, new_tag(soup, "br"))
            del img["width"]
            del img["height"]
            img.extract()
            div.insert(2, img)
            table.replaceWith(div)
        return soup

    def canonicalize_internal_url(self, url, is_link=True):
        if url.endswith("/print"):
            url = url.rpartition("/")[0]
        return BasicNewsRecipe.canonicalize_internal_url(self, url, is_link=is_link)
