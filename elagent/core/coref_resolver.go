package elagent

import (
	"fmt"
	"strings"
)

// CorefPair 共指对
type CorefPair struct {
	Pronoun      string // 代词文本（如"她"）
	PronounStart int    // 代词起始位置
	PronounEnd   int    // 代词结束位置
	Entity       string // 回链到的实体名
	EntityID     string // 回链到的实体ID
	Confidence   float64
}

var personalPronouns = map[string]string{
	"她": "PER", "他": "PER", "她们": "PER", "他们": "PER",
	"它": "ORG", "其": "PER",
}

var demonstrativePatterns = []struct {
	Pattern string
	Type    string
}{
	{"本次赛事", "EVENT"}, {"该赛事", "EVENT"}, {"本届赛事", "EVENT"},
	{"该队", "ORG"}, {"该组合", "ORG"}, {"该支队", "ORG"},
	{"该选手", "PER"}, {"这位选手", "PER"}, {"该运动员", "PER"},
	{"该地区", "LOC"}, {"该城市", "LOC"}, {"该省", "LOC"}, {"该国", "LOC"},
}

// ResolveArticleCoref 对文章全文做一次共指消解
func ResolveArticleCoref(fullText string, existingMentions []Mention) []CorefPair {
	var results []CorefPair
	textRunes := []rune(fullText)

	// 1. 人称代词
	for pronoun, etype := range personalPronouns {
		start := 0
		for {
			idx := strings.Index(fullText[start:], pronoun)
			if idx == -1 {
				break
			}
			absStart := start + idx
			absEnd := absStart + len(pronoun)

			// 找最近同类型前序mention
			target := findNearestPrev(etype, absStart, existingMentions, results)
			if target != nil {
				results = append(results, CorefPair{
					Pronoun: pronoun, PronounStart: absStart, PronounEnd: absEnd,
					Entity: target.Entity, EntityID: target.EntityID, Confidence: 0.95,
				})
			}
			start = absEnd
		}
	}

	// 2. 指示代词
	for _, dp := range demonstrativePatterns {
		start := 0
		for {
			idx := strings.Index(fullText[start:], dp.Pattern)
			if idx == -1 {
				break
			}
			absStart := start + idx
			absEnd := absStart + len(dp.Pattern)

			target := findNearestPrev(dp.Type, absStart, existingMentions, results)
			if target != nil {
				results = append(results, CorefPair{
					Pronoun: dp.Pattern, PronounStart: absStart, PronounEnd: absEnd,
					Entity: target.Entity, EntityID: target.EntityID, Confidence: 0.90,
				})
			}
			start = absEnd
		}
	}

	_ = textRunes
	return results
}

func findNearestPrev(etype string, pos int, mentions []Mention, corefs []CorefPair) *CorefPair {
	// 先找非代词的mention
	for i := len(mentions) - 1; i >= 0; i-- {
		if mentions[i].End <= pos && mentions[i].EntityType == etype {
			return &CorefPair{Entity: mentions[i].Text, EntityID: mentions[i].EntityID}
		}
	}
	// 兜底：找已消解的代词
	for i := len(corefs) - 1; i >= 0; i-- {
		if corefs[i].PronounEnd <= pos {
			return &CorefPair{Entity: corefs[i].Entity, EntityID: corefs[i].EntityID}
		}
	}
	return nil
}

// Mention 简化的mention结构
type Mention struct {
	Text       string
	Start      int
	End        int
	EntityType string
	EntityID   string
}
