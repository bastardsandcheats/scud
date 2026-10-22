from scud.matcher import fold, episode_numbers, guess_file
from scud.zurg_compat import parse_name, read_numbering, bare_title

def test_episode_numbering():
    assert episode_numbers('Show.S02E04.1080p.mkv')==(2,4,None)
    assert episode_numbers('Show 3x07.mkv')==(3,7,None)
    assert episode_numbers('Movie.x265.mkv')==(None,None,None)

def test_episode_ranges_and_spelled_season():
    assert episode_numbers('Show.S01E01-E10.mkv')==(1,1,10)
    assert episode_numbers('Show Season 5 Episode 08.mkv')==(5,8,None)

def test_tv_uses_top_folder():
    g=guess_file({'type':'show'},'The Office (US)/Season 02/The.Office.US.S02E04.mkv')
    assert g.title=='The Office US' and g.season==2 and g.episode==4

def test_movie_title_and_year():
    g=guess_file({'type':'movie'},'The.Thing.1982.1080p.BluRay.mkv')
    assert g.title=='The Thing' and g.year==1982

def test_zurg_fold_semantics():
    assert bare_title("It's a Wonderful Life") == bare_title('Its.A.Wonderful.Life')
    assert bare_title('Tales of Ladybug & Cat Noir') == bare_title('Tales of Ladybug and Cat Noir')
    assert fold('The Thing')==fold('Thing')

def test_absolute_anime_numbering_marks_show():
    p=parse_name('Fairy.Tail.E101.1080p.WEB-DL')
    assert p.show and p.title=='fairy tail'
