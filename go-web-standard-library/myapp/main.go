package main

import (
	"fmt"
	"html/template"
	"log"
	"net/http"
	"runtime"
	"time"
)

var templates *template.Template

func init() {
	templates = template.Must(template.ParseGlob("templates/*.html"))
}

func main() {
	mux := http.NewServeMux()

	// 静的ファイルの配信を追加
	fs := http.FileServer(http.Dir("static"))
	mux.Handle("GET /static/", http.StripPrefix("/static/", fs))

	// ルート
	mux.HandleFunc("GET /", homeHandler)
	mux.HandleFunc("GET /about", aboutHandler)
	mux.HandleFunc("GET /users/{id}", userHandler)
	mux.HandleFunc("GET /contact", contactFormHandler)
	mux.HandleFunc("POST /contact", contactSubmitHandler)

	log.Println("Server starting on http://localhost:8080")

	server := &http.Server{
		Addr:         ":8080",
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	log.Fatal(server.ListenAndServe())
}

func renderTemplate(w http.ResponseWriter, tmplName string, data map[string]any) {
	err := templates.ExecuteTemplate(w, tmplName, data)
	if err != nil {
		http.Error(w, "テンプレートエラー", http.StatusInternalServerError)
	}
}

func homeHandler(w http.ResponseWriter, r *http.Request) {
	data := map[string]any{
		"Title":   "Goで作るWebサイト",
		"Message": "標準ライブラリだけで作りました！",
		"Items":   []string{"シンプル", "高速", "安全"},
	}
	renderTemplate(w, "layout.html", data)
}

func aboutHandler(w http.ResponseWriter, r *http.Request) {
	data := map[string]any{
		"Title":     "About",
		"GoVersion": runtime.Version(),
	}
	renderTemplate(w, "layout.html", data)
}

func userHandler(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	fmt.Fprintf(w, "ユーザーID: %s", id)
}

func contactFormHandler(w http.ResponseWriter, r *http.Request) {
	data := map[string]any{
		"Title": "お問い合わせ",
	}
	renderTemplate(w, "layout.html", data)
}

func contactSubmitHandler(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseForm(); err != nil {
		http.Error(w, "フォームの解析に失敗しました", http.StatusBadRequest)
		return
	}

	name := r.FormValue("name")
	email := r.FormValue("email")
	message := r.FormValue("message")

	fmt.Fprintf(w, "ありがとうございます、%sさん！\n", name)
	fmt.Fprintf(w, "メール: %s\n", email)
	fmt.Fprintf(w, "メッセージ: %s\n", message)
}
