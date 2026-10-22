import logging
import unittest
from unittest.mock import Mock
from scud.matcher import Matcher, guess_name
from scud.tmdb import TMDBError

class MatchSuggestionTests(unittest.TestCase):
    def setUp(self):self.matcher=Matcher(Mock(),logging.getLogger())
    def test_release_name_cleanup(self):
        guess=guess_name('Tarzan.II.(2005).1080p.crtani.filmovi.hrvatski.sink.[remastered]','movie')
        self.assertEqual((guess.title,guess.year),('Tarzan II',2005))
        guess=guess_name('[Group] Star.Trek.Deep.Space.Nine.S01E01.1080p.mkv','show')
        self.assertEqual(guess.title,'Star Trek Deep Space Nine')
    def test_failed_folder_uses_filename(self):
        self.matcher.match=Mock(side_effect=[{'status':'unmatched'},{'status':'matched','method':'exact','ids':{'imdb':'tt0084787'}}])
        result=self.matcher.match_file({'type':'movie'},'Unknown/The.Thing.1982.1080p.mkv')
        self.assertEqual(result['status'],'matched')
        self.assertEqual(result['method'],'filename-exact')
        self.assertEqual(self.matcher.match.call_args_list[1].args[0].title,'The Thing')
    def test_folder_match_wins(self):
        self.matcher.match=Mock(return_value={'status':'matched','method':'exact'})
        self.matcher.match_file({'type':'movie'},'Known (2000)/Other.2001.mkv')
        self.matcher.match.assert_called_once()
    def test_suggestions_filter_kind_deduplicate_and_include_sequel_alternative(self):
        self.matcher.search=Mock(return_value={'results':[
            {'searchTitle':'Tarzan II','year':2005,'type':'movie','tmdb_id':'15657'},
            {'searchTitle':'Tarzan','year':1999,'type':'movie','tmdb_id':'37135'},
            {'searchTitle':'Tarzan','year':2003,'type':'show','tmdb_id':'111'},
        ]})
        rows,errors=self.matcher.suggestions([(guess_name('Tarzan.II.2005.1080p','movie'),'Filename')])
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['id'],'tmdb://15657');self.assertEqual(rows[0]['source'],'Filename')
        self.assertIn('tarzan 2 movie',[call.args[0] for call in self.matcher.search.call_args_list])
        self.assertEqual(errors,[])
    def test_service_failure_is_explained(self):
        self.matcher.search=Mock(side_effect=TMDBError('TMDB is unavailable'))
        rows,errors=self.matcher.suggestions([(guess_name('Movie.2000','movie'),'Folder')])
        self.assertEqual(rows,[]);self.assertTrue(errors)
