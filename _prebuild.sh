# change py files to .recipe
for rcp in 'ft' 'joongangdaily' 'politico-magazine' 'channelnewsasia' 'scmp' 'thediplomat' 'wapo' 'nytimes-global' 'nytimes-books' 'fivebooks'
do
    cp -p "$rcp.recipe.py" "$rcp.recipe"
done
