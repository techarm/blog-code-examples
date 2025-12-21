package main

import (
	"encoding/json"
	"log"
	"net/http"
	"strconv"
	"sync"
	"time"
)

type Snippet struct {
	ID        int       `json:"id"`
	Title     string    `json:"title"`
	Code      string    `json:"code"`
	Language  string    `json:"language"`
	CreatedAt time.Time `json:"created_at"`
}

// エラーレスポンス用の構造体
type ErrorResponse struct {
	Error   string `json:"error"`
	Message string `json:"message,omitempty"`
}

// インメモリストア
var (
	snippets = make(map[int]Snippet)
	nextID   = 1
	mu       sync.RWMutex
)

func main() {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", healthHandler)
	mux.HandleFunc("GET /snippets", listSnippets)
	mux.HandleFunc("GET /snippets/{id}", getSnippet)
	mux.HandleFunc("POST /snippets", createSnippet)
	mux.HandleFunc("PUT /snippets/{id}", updateSnippet)
	mux.HandleFunc("DELETE /snippets/{id}", deleteSnippet)

	log.Println("Server starting on http://localhost:8080")

	server := &http.Server{
		Addr:         ":8080",
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	log.Fatal(server.ListenAndServe())
}

// エラーレスポンスを返すヘルパー関数
func respondError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(ErrorResponse{Error: http.StatusText(status), Message: message})
}

// JSONレスポンスを返すヘルパー関数
func respondJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	respondJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func createSnippet(w http.ResponseWriter, r *http.Request) {
	var input struct {
		Title    string `json:"title"`
		Code     string `json:"code"`
		Language string `json:"language"`
	}

	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		respondError(w, http.StatusBadRequest, "Invalid JSON")
		return
	}

	// バリデーション
	if input.Title == "" || input.Code == "" {
		respondError(w, http.StatusBadRequest, "title and code are required")
		return
	}

	mu.Lock()
	snippet := Snippet{
		ID:        nextID,
		Title:     input.Title,
		Code:      input.Code,
		Language:  input.Language,
		CreatedAt: time.Now(),
	}
	snippets[nextID] = snippet
	nextID++
	mu.Unlock()

	respondJSON(w, http.StatusCreated, snippet)
}

func listSnippets(w http.ResponseWriter, r *http.Request) {
	mu.RLock()
	result := make([]Snippet, 0, len(snippets))
	for _, s := range snippets {
		result = append(result, s)
	}
	mu.RUnlock()

	respondJSON(w, http.StatusOK, result)
}

func getSnippet(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		respondError(w, http.StatusBadRequest, "Invalid ID")
		return
	}

	mu.RLock()
	snippet, exists := snippets[id]
	mu.RUnlock()

	if !exists {
		respondError(w, http.StatusNotFound, "Snippet not found")
		return
	}

	respondJSON(w, http.StatusOK, snippet)
}

func updateSnippet(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		respondError(w, http.StatusBadRequest, "Invalid ID")
		return
	}

	var input struct {
		Title    string `json:"title"`
		Code     string `json:"code"`
		Language string `json:"language"`
	}

	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		respondError(w, http.StatusBadRequest, "Invalid JSON")
		return
	}

	mu.Lock()
	snippet, exists := snippets[id]
	if !exists {
		mu.Unlock()
		respondError(w, http.StatusNotFound, "Snippet not found")
		return
	}

	// 更新（空でなければ上書き）
	if input.Title != "" {
		snippet.Title = input.Title
	}
	if input.Code != "" {
		snippet.Code = input.Code
	}
	if input.Language != "" {
		snippet.Language = input.Language
	}

	snippets[id] = snippet
	mu.Unlock()

	respondJSON(w, http.StatusOK, snippet)
}

func deleteSnippet(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		respondError(w, http.StatusBadRequest, "Invalid ID")
		return
	}

	mu.Lock()
	_, exists := snippets[id]
	if !exists {
		mu.Unlock()
		respondError(w, http.StatusNotFound, "Snippet not found")
		return
	}

	delete(snippets, id)
	mu.Unlock()

	w.WriteHeader(http.StatusNoContent)
}
