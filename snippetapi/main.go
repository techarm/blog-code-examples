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

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func createSnippet(w http.ResponseWriter, r *http.Request) {
	var input struct {
		Title    string `json:"title"`
		Code     string `json:"code"`
		Language string `json:"language"`
	}

	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		http.Error(w, `{"error":"Invalid JSON"}`, http.StatusBadRequest)
		return
	}

	// バリデーション
	if input.Title == "" || input.Code == "" {
		http.Error(w, `{"error":"title and code are required"}`, http.StatusBadRequest)
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

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(snippet)
}

func listSnippets(w http.ResponseWriter, r *http.Request) {
	mu.RLock()
	result := make([]Snippet, 0, len(snippets))
	for _, s := range snippets {
		result = append(result, s)
	}
	mu.RUnlock()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func getSnippet(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		http.Error(w, `{"error":"Invalid ID"}`, http.StatusBadRequest)
		return
	}

	mu.RLock()
	snippet, exists := snippets[id]
	mu.RUnlock()

	if !exists {
		http.Error(w, `{"error":"Snippet not found"}`, http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(snippet)
}

func updateSnippet(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		http.Error(w, `{"error":"Invalid ID"}`, http.StatusBadRequest)
		return
	}

	var input struct {
		Title    string `json:"title"`
		Code     string `json:"code"`
		Language string `json:"language"`
	}

	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		http.Error(w, `{"error":"Invalid JSON"}`, http.StatusBadRequest)
		return
	}

	mu.Lock()
	snippet, exists := snippets[id]
	if !exists {
		mu.Unlock()
		http.Error(w, `{"error":"Snippet not found"}`, http.StatusNotFound)
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

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(snippet)
}

func deleteSnippet(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		http.Error(w, `{"error":"Invalid ID"}`, http.StatusBadRequest)
		return
	}

	mu.Lock()
	_, exists := snippets[id]
	if !exists {
		mu.Unlock()
		http.Error(w, `{"error":"Snippet not found"}`, http.StatusNotFound)
		return
	}

	delete(snippets, id)
	mu.Unlock()

	w.WriteHeader(http.StatusNoContent)
}
