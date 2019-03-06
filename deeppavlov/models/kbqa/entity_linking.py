# Copyright 2017 Neural Networks and Deep Learning lab, MIPT
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from fuzzywuzzy import fuzz
import pymorphy2
import itertools
from logging import getLogger
from typing import List, Dict, Tuple

log = getLogger(__name__)


class EntityLinker:
    def __init__(self, name_to_q: Dict[str, List[Tuple[str]]], wikidata: Dict[str, List[List[str]]],
                 lemmatize: bool = True, debug: bool = False, rule_filter_entities: bool = True) -> None:
        self.name_to_q = name_to_q
        self.wikidata = wikidata
        self.morph = pymorphy2.MorphAnalyzer()
        self.lemmatize = lemmatize
        self.debug = debug
        self.rule_filter_entities = rule_filter_entities

    def __call__(self, entity: str, question_tokens: List[str]) -> Tuple[List[List[List[str]]], List[str]]:

        confidences = []
        if not entity:
            wiki_entities = ["None"]
        else:
            candidate_entities = self.find_candidate_entities(entity)

            srtd_cand_ent = sorted(candidate_entities, key=lambda x: x[2], reverse=True)
            if len(srtd_cand_ent) > 0:
                wiki_entities = [srtd_cand_ent[i][1] for i in range(len(srtd_cand_ent))]
                if self.debug:
                    log.info("wiki entities %s" % (str(wiki_entities[:5])))
                confidences = [1.0 for i in range(len(srtd_cand_ent))]
            else:
                candidates = self.substring_entity_search(entity)
                candidates = list(set(candidates))
                srtd_cand_ent = sorted(candidates, key=lambda x: x[2], reverse=True)
                if len(srtd_cand_ent) > 0:
                    wiki_entities = [srtd_cand_ent[i][1] for i in range(len(srtd_cand_ent))]
                    if self.debug:
                        log.info("wiki entities %s" % (str(wiki_entities[:5])))
                else:
                    candidates = self.fuzzy_entity_search(entity)
                    candidates = list(set(candidates))
                    srtd_cand_ent = sorted(candidates, key=lambda x: x[1], reverse=True)

                    if len(srtd_cand_ent) > 0:
                        wiki_entities = [srtd_cand_ent[i][0][1] for i in range(len(srtd_cand_ent))]
                        if self.debug:
                            log.info("wiki entities %s" % (str(wiki_entities[:5])))
                        confidences = [float(srtd_cand_ent[i][1]) * 0.01 for i in range(len(srtd_cand_ent))]
                    else:
                        wiki_entities = ["None"]
                        confidences = [0.0]

        entity_triplets = self.extract_triplets_from_wiki(wiki_entities)
        if self.rule_filter_entities:
            filtered_entity_triplets = self.filter_triplets(entity_triplets, question_tokens)

        return filtered_entity_triplets, confidences

    def find_candidate_entities(self, entity: str) -> List[str]:
        candidate_entities = []
        candidate_entities += self.name_to_q.get(entity, [])
        entity_split = entity.split(' ')
        if len(entity_split) < 6 and self.lemmatize:
            entity_lemm_tokens = []
            for tok in entity_split:
                morph_parse_tok = self.morph.parse(tok)[0]
                lemmatized_tok = morph_parse_tok.normal_form
                entity_lemm_tokens.append(lemmatized_tok)
            masks = itertools.product('01', repeat=len(entity_split))
            for mask in masks:
                entity_lemm = []
                for i in range(len(entity_split)):
                    if mask[i] == 0:
                        entity_lemm.append(entity_split[i])
                    else:
                        entity_lemm.append(entity_lemm_tokens[i])
                entity_lemm = ' '.join(entity_lemm)
                if entity_lemm != entity:
                    candidate_entities += self.name_to_q.get(entity_lemm, [])

        return candidate_entities

    def fuzzy_entity_search(self, entity: str) -> List[Tuple[Tuple, str]]:
        word_length = len(entity)
        candidates = []
        for title in self.name_to_q:
            length_ratio = len(title) / word_length
            if length_ratio > 0.5 and length_ratio < 1.5:
                ratio = fuzz.ratio(title, entity)
                if ratio > 50:
                    entity_candidates = self.name_to_q.get(title, [])
                    for cand in entity_candidates:
                        candidates.append((cand, fuzz.ratio(entity, cand[0])))
        return candidates

    def substring_entity_search(self, entity: str) -> List[Tuple[str]]:
        entity_lower = entity.lower()
        candidates = []
        for title in self.name_to_q:
            if title.find(entity_lower) > -1:
                entity_candidates = self.name_to_q.get(title, [])
                for cand in entity_candidates:
                    candidates.append(cand)
        return candidates

    def extract_triplets_from_wiki(self, entity_ids: List[str]) -> List[List[List[str]]]:
        entity_triplets = []
        for entity_id in entity_ids:
            if entity_id in self.wikidata and entity_id.startswith('Q'):
                triplets_for_entity = self.wikidata[entity_id]
                entity_triplets.append(triplets_for_entity)
            else:
                entity_triplets.append([])

        return entity_triplets

    @staticmethod
    def filter_triplets(entity_triplets: List[List[List[str]]], question_tokens: List[str]) -> \
            List[List[List[str]]]:
        question_begin = question_tokens[0].lower() + ' ' + question_tokens[1].lower()
        what_is_templates = ['что такое', 'что есть', 'что означает', 'что значит']
        filtered_entity_triplets = []
        for triplets_for_entity in entity_triplets:
            entity_is_human = False
            property_is_instance_of = "P31"
            id_for_entity_human = "Q5"
            for triplet in triplets_for_entity:
                if triplet[0] == property_is_instance_of and triplet[1] == id_for_entity_human:
                    entity_is_human = True
                    break
            if question_begin in what_is_templates and entity_is_human:
                continue
            filtered_entity_triplets.append(triplets_for_entity)

        return filtered_entity_triplets