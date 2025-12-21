package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// テスト前にデータをリセットするヘルパー関数
func resetTestData() {
	mu.Lock()
	snippets = make(map[int]Snippet)
	nextID = 1
	mu.Unlock()
}

// テスト用のスニペットを作成するヘルパー関数
func createTestSnippet(title, code, language string) Snippet {
	mu.Lock()
	defer mu.Unlock()

	snippet := Snippet{
		ID:       nextID,
		Title:    title,
		Code:     code,
		Language: language,
	}
	snippets[nextID] = snippet
	nextID++
	return snippet
}

func TestHealthHandler(t *testing.T) {
	req := httptest.NewRequest("GET", "/health", nil)
	rec := httptest.NewRecorder()

	healthHandler(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("expected status %d, got %d", http.StatusOK, rec.Code)
	}

	var response map[string]string
	json.NewDecoder(rec.Body).Decode(&response)

	if response["status"] != "ok" {
		t.Errorf("expected status 'ok', got '%s'", response["status"])
	}
}

func TestListSnippets(t *testing.T) {
	resetTestData()
	createTestSnippet("Test1", "code1", "go")
	createTestSnippet("Test2", "code2", "python")

	req := httptest.NewRequest("GET", "/snippets", nil)
	rec := httptest.NewRecorder()

	listSnippets(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("expected status %d, got %d", http.StatusOK, rec.Code)
	}

	var result []Snippet
	json.NewDecoder(rec.Body).Decode(&result)

	if len(result) != 2 {
		t.Errorf("expected 2 snippets, got %d", len(result))
	}
}

func TestGetSnippet(t *testing.T) {
	resetTestData()
	created := createTestSnippet("Test", "code", "go")

	req := httptest.NewRequest("GET", "/snippets/1", nil)
	req.SetPathValue("id", "1")
	rec := httptest.NewRecorder()

	getSnippet(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("expected status %d, got %d", http.StatusOK, rec.Code)
	}

	var snippet Snippet
	json.NewDecoder(rec.Body).Decode(&snippet)

	if snippet.Title != created.Title {
		t.Errorf("expected title '%s', got '%s'", created.Title, snippet.Title)
	}
}

func TestGetSnippetNotFound(t *testing.T) {
	resetTestData()

	req := httptest.NewRequest("GET", "/snippets/999", nil)
	req.SetPathValue("id", "999")
	rec := httptest.NewRecorder()

	getSnippet(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Errorf("expected status %d, got %d", http.StatusNotFound, rec.Code)
	}
}

func TestCreateSnippet(t *testing.T) {
	resetTestData()

	body := `{"title":"Test","code":"test code","language":"go"}`
	req := httptest.NewRequest("POST", "/snippets", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	createSnippet(rec, req)

	if rec.Code != http.StatusCreated {
		t.Errorf("expected status %d, got %d", http.StatusCreated, rec.Code)
	}

	var snippet Snippet
	json.NewDecoder(rec.Body).Decode(&snippet)

	if snippet.Title != "Test" {
		t.Errorf("expected title 'Test', got '%s'", snippet.Title)
	}
}

func TestCreateSnippetValidation(t *testing.T) {
	resetTestData()

	body := `{"code":"test code"}`
	req := httptest.NewRequest("POST", "/snippets", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	createSnippet(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Errorf("expected status %d, got %d", http.StatusBadRequest, rec.Code)
	}
}

func TestUpdateSnippet(t *testing.T) {
	resetTestData()
	createTestSnippet("Original", "code", "go")

	body := `{"title":"Updated"}`
	req := httptest.NewRequest("PUT", "/snippets/1", bytes.NewBufferString(body))
	req.SetPathValue("id", "1")
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	updateSnippet(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("expected status %d, got %d", http.StatusOK, rec.Code)
	}

	var snippet Snippet
	json.NewDecoder(rec.Body).Decode(&snippet)

	if snippet.Title != "Updated" {
		t.Errorf("expected title 'Updated', got '%s'", snippet.Title)
	}
}

func TestUpdateSnippetNotFound(t *testing.T) {
	resetTestData()

	body := `{"title":"Updated"}`
	req := httptest.NewRequest("PUT", "/snippets/999", bytes.NewBufferString(body))
	req.SetPathValue("id", "999")
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	updateSnippet(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Errorf("expected status %d, got %d", http.StatusNotFound, rec.Code)
	}
}

func TestDeleteSnippet(t *testing.T) {
	resetTestData()
	createTestSnippet("ToDelete", "code", "go")

	req := httptest.NewRequest("DELETE", "/snippets/1", nil)
	req.SetPathValue("id", "1")
	rec := httptest.NewRecorder()

	deleteSnippet(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Errorf("expected status %d, got %d", http.StatusNoContent, rec.Code)
	}

	// 削除されたことを確認
	mu.RLock()
	_, exists := snippets[1]
	mu.RUnlock()

	if exists {
		t.Error("snippet should be deleted")
	}
}

func TestDeleteSnippetNotFound(t *testing.T) {
	resetTestData()

	req := httptest.NewRequest("DELETE", "/snippets/999", nil)
	req.SetPathValue("id", "999")
	rec := httptest.NewRecorder()

	deleteSnippet(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Errorf("expected status %d, got %d", http.StatusNotFound, rec.Code)
	}
}
